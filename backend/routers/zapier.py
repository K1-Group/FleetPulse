"""Zapier integration endpoints for FleetPulse.

Zapier is an orchestration layer here. These endpoints expose read-only Geotab
projections and an optional outbound webhook push; they do not write back to
Geotab or FleetPulse state.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from services.fleet_service import get_fleet_overview, get_location_stats, get_vehicles
from services.safety_service import get_safety_scores

router = APIRouter()

SIGNATURE_ALGORITHM = "hmac-sha256-canonical-json-v1"
SIGNATURE_FIELDS = {
    "payload_signature",
    "signature_algorithm",
    "teams_message",
    "teams_message_signature",
}


class ZapierVerifyRequest(BaseModel):
    payload: dict[str, Any]
    signature: str | None = None


class ZapierVerifyMessageRequest(BaseModel):
    message: str
    signature: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _minute_key() -> str:
    return _now().strftime("%Y%m%dT%H%MZ")


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _dump(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    raise TypeError(f"Unsupported Zapier row type: {type(value).__name__}")


def _flatten_vehicle(value: Any) -> dict[str, Any]:
    row = _dump(value)
    position = row.pop("position", None) or {}
    row["latitude"] = position.get("latitude")
    row["longitude"] = position.get("longitude")
    row["bearing"] = position.get("bearing")
    row["speed"] = position.get("speed")
    return row


def _flatten_safety_score(value: Any, days: int) -> dict[str, Any]:
    row = _dump(value)
    breakdown = row.pop("breakdown", None) or {}
    row["speeding_events"] = breakdown.get("speeding", 0)
    row["harsh_braking_events"] = breakdown.get("harsh_braking", 0)
    row["harsh_acceleration_events"] = breakdown.get("harsh_acceleration", 0)
    row["harsh_cornering_events"] = breakdown.get("harsh_cornering", 0)
    row["period_days"] = days
    return row


def _build_snapshot(days: int) -> dict[str, Any]:
    overview = _dump(get_fleet_overview())
    locations = [_dump(location) for location in get_location_stats()]
    vehicles = [_flatten_vehicle(vehicle) for vehicle in get_vehicles()]
    safety_scores = [_flatten_safety_score(score, days) for score in get_safety_scores(days=days)]
    risk_scores = sorted(
        safety_scores,
        key=lambda item: (float(item.get("score", 100)), -int(item.get("event_count", 0))),
    )
    top_risk = risk_scores[0] if risk_scores else {}

    return {
        "id": f"fleetpulse-snapshot-{_minute_key()}",
        "event_type": "fleetpulse.snapshot",
        "source_system": "FleetPulse",
        "source_authority": "Geotab",
        "projection_mode": "read_only",
        "exported_at": _now_iso(),
        "period_days": days,
        "overview": overview,
        "row_counts": {
            "locations": len(locations),
            "vehicles": len(vehicles),
            "safety_scores": len(safety_scores),
        },
        "top_risk_vehicle_id": top_risk.get("vehicle_id"),
        "top_risk_vehicle_name": top_risk.get("vehicle_name"),
        "top_risk_score": top_risk.get("score"),
        "top_risk_event_count": top_risk.get("event_count"),
    }


def _risk_vehicle_rows(days: int, max_score: float, min_events: int, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for score in get_safety_scores(days=days):
        row = _flatten_safety_score(score, days)
        score_value = float(row.get("score") or 100)
        event_count = int(row.get("event_count") or 0)
        if score_value > max_score or event_count < min_events:
            continue
        vehicle_id = row.get("vehicle_id") or row.get("vehicle_name") or "unknown"
        rows.append(
            {
                **row,
                "id": f"fleetpulse-risk-{vehicle_id}-{days}-{score_value}-{event_count}",
                "event_type": "fleetpulse.risk_vehicle",
                "source_system": "FleetPulse",
                "source_authority": "Geotab",
                "projection_mode": "read_only",
                "exported_at": _now_iso(),
            }
        )
    rows.sort(key=lambda item: (float(item.get("score", 100)), -int(item.get("event_count", 0))))
    return rows[:limit]


def _zapier_config() -> dict[str, Any]:
    webhook_url = os.getenv("FLEETPULSE_ZAPIER_WEBHOOK_URL", "")
    return {
        "enabled": _bool_env("FLEETPULSE_ZAPIER_ENABLED"),
        "webhook_configured": bool(webhook_url),
        "api_key_required": bool(os.getenv("FLEETPULSE_ZAPIER_API_KEY")),
        "signing_enabled": bool(os.getenv("FLEETPULSE_ZAPIER_SHARED_SECRET")),
        "timeout_seconds": int(os.getenv("FLEETPULSE_ZAPIER_TIMEOUT_SECONDS", "15")),
    }


def _require_api_key(x_fleetpulse_zapier_key: Optional[str], x_api_key: Optional[str]) -> None:
    expected = os.getenv("FLEETPULSE_ZAPIER_API_KEY")
    if not expected:
        return
    provided = x_fleetpulse_zapier_key or x_api_key
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="invalid_zapier_api_key")


def _signature(body: str) -> str | None:
    secret = os.getenv("FLEETPULSE_ZAPIER_SHARED_SECRET")
    if not secret:
        return None
    digest = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _message_signature(message: str) -> str | None:
    return _signature(f"fleetpulse-teams-message-v1:{message}")


def _build_teams_message(payload: dict[str, Any]) -> str:
    row_counts = payload.get("row_counts") or {}
    overview = payload.get("overview") or {}
    return "\n".join(
        [
            "FleetPulse Snapshot",
            f"Payload: {payload.get('id', '')}",
            f"Vehicles: {row_counts.get('vehicles', '')}",
            f"Locations: {row_counts.get('locations', '')}",
            f"Authority: {payload.get('source_authority', '')}",
            f"Mode: {payload.get('projection_mode', '')}",
            f"Exported: {payload.get('exported_at', '')}",
            f"Top Risk: {payload.get('top_risk_vehicle_name', '')} ({payload.get('top_risk_score', '')})",
            f"Active: {overview.get('active', '')}",
            f"Parked: {overview.get('parked', '')}",
            f"Offline: {overview.get('offline', '')}",
        ]
    )


def _canonical_payload_body(payload: dict[str, Any]) -> str:
    unsigned_payload = {key: value for key, value in payload.items() if key not in SIGNATURE_FIELDS}
    return json.dumps(unsigned_payload, sort_keys=True, separators=(",", ":"))


def _attach_payload_signature(payload: dict[str, Any]) -> dict[str, Any]:
    signed_payload = dict(payload)
    body = _canonical_payload_body(signed_payload)
    signature = _signature(body)
    if signature:
        signed_payload["signature_algorithm"] = SIGNATURE_ALGORITHM
        signed_payload["payload_signature"] = signature
        teams_message = _build_teams_message(signed_payload)
        teams_message_signature = _message_signature(teams_message)
        if teams_message_signature:
            signed_payload["teams_message"] = teams_message
            signed_payload["teams_message_signature"] = teams_message_signature
    return signed_payload


def _verify_payload_signature(payload: dict[str, Any], signature: str | None = None) -> bool:
    expected = _signature(_canonical_payload_body(payload))
    provided = signature or payload.get("payload_signature")
    if not expected or not isinstance(provided, str):
        return False
    return hmac.compare_digest(provided, expected)


def _verify_message_signature(message: str, signature: str) -> bool:
    expected = _message_signature(message)
    if not expected:
        return False
    return hmac.compare_digest(signature, expected)


async def _post_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    webhook_url = os.getenv("FLEETPULSE_ZAPIER_WEBHOOK_URL")
    if not webhook_url:
        raise HTTPException(status_code=409, detail="zapier_webhook_not_configured")

    signed_payload = _attach_payload_signature(payload)
    body = json.dumps(signed_payload, sort_keys=True, separators=(",", ":"))
    headers = {"Content-Type": "application/json"}
    signature = _signature(body)
    if signature:
        headers["X-FleetPulse-Signature"] = signature

    timeout = int(os.getenv("FLEETPULSE_ZAPIER_TIMEOUT_SECONDS", "15"))
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(webhook_url, content=body, headers=headers)
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "zapier_webhook_failed",
                "status_code": response.status_code,
                "body": response.text[:500],
            },
        )
    return {
        "status": "sent",
        "zapier_status_code": response.status_code,
        "payload_id": signed_payload.get("id"),
    }


@router.get("/status")
async def zapier_status() -> dict[str, Any]:
    """Show Zapier integration readiness without exposing secrets."""
    return {
        "status": "ok",
        "integration": "zapier",
        "source_system": "FleetPulse",
        "source_authority": "Geotab",
        "projection_mode": "read_only",
        **_zapier_config(),
        "endpoints": {
            "poll_snapshot": "/api/zapier/triggers/fleet-snapshot",
            "poll_risk_vehicles": "/api/zapier/triggers/risk-vehicles",
            "push_snapshot": "/api/zapier/actions/push-snapshot",
            "verify_snapshot": "/api/zapier/actions/verify-snapshot",
            "verify_message": "/api/zapier/actions/verify-message",
        },
    }


@router.get("/triggers/fleet-snapshot")
async def fleet_snapshot_trigger(days: int = Query(7, ge=1, le=90)) -> list[dict[str, Any]]:
    """Zapier polling trigger: one snapshot row per poll window."""
    return [_build_snapshot(days)]


@router.get("/triggers/risk-vehicles")
async def risk_vehicles_trigger(
    days: int = Query(7, ge=1, le=90),
    max_score: float = Query(85, ge=0, le=100),
    min_events: int = Query(1, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> list[dict[str, Any]]:
    """Zapier polling trigger: vehicles below safety threshold."""
    return _risk_vehicle_rows(days, max_score, min_events, limit)


@router.post("/actions/push-snapshot")
async def push_snapshot_action(
    days: int = Query(7, ge=1, le=90),
    x_fleetpulse_zapier_key: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """Push a FleetPulse snapshot to a configured Zapier Catch Hook."""
    if not _bool_env("FLEETPULSE_ZAPIER_ENABLED"):
        raise HTTPException(status_code=409, detail="zapier_push_disabled")
    _require_api_key(x_fleetpulse_zapier_key, x_api_key)
    payload = _build_snapshot(days)
    return await _post_webhook(payload)


@router.post("/actions/verify-snapshot")
async def verify_snapshot_action(request: ZapierVerifyRequest) -> dict[str, Any]:
    """Verify a pushed FleetPulse Catch Hook payload without exposing the signing secret."""
    valid = _verify_payload_signature(request.payload, request.signature)
    return {
        "status": "ok" if valid else "invalid",
        "valid": valid,
        "source_system": request.payload.get("source_system"),
        "source_authority": request.payload.get("source_authority"),
        "projection_mode": request.payload.get("projection_mode"),
        "event_type": request.payload.get("event_type"),
        "payload_id": request.payload.get("id"),
        "signature_algorithm": request.payload.get("signature_algorithm"),
    }


@router.post("/actions/verify-message")
async def verify_message_action(request: ZapierVerifyMessageRequest) -> dict[str, Any]:
    """Verify the compact Teams message generated by FleetPulse for Zapier routing."""
    valid = _verify_message_signature(request.message, request.signature)
    return {
        "status": "ok" if valid else "invalid",
        "valid": valid,
        "teams_message": request.message if valid else "",
    }
