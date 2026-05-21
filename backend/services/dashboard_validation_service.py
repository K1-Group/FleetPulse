"""Dashboard source validation for visible FleetPulse metrics.

This module produces a read-only validation contract for the dashboard. It
does not mutate source systems and it deliberately avoids marking placeholder,
empty, stale, demo, or blocked data as verified.
"""

from __future__ import annotations

import os
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from configs.operating_system import OperatingSystemRuntimeConfig
from services.alert_service import get_recent_alerts
from services.fleet_service import get_fleet_overview, get_location_stats, get_vehicles
from services.driver_workforce_service import get_driver_workforce_dataset
from services.k1l_operating_kpi_service import (
    POWERBI_REVENUE_SOURCE,
    WAREHOUSE_SQL_REVENUE_SOURCE,
    get_k1l_operating_kpi_snapshot,
)
from services.safety_service import get_safety_scores
from services.monitor_service import get_monitor_status
from services.validation_audit_service import audit_contract_ok, last_seen_row_at, record_probe


ValidationItem = dict[str, Any]

OVERVIEW_METRICS = [
    ("total_vehicles", "Total Vehicles"),
    ("active", "Active"),
    ("idle", "Idle"),
    ("parked", "Parked"),
    ("total_trips_today", "Driver Trips"),
    ("total_stops_today", "Stops >5m"),
    ("total_distance_miles", "Distance (mi)"),
    ("avg_trip_duration_hours", "Avg Trip Hrs"),
    ("avg_trip_distance_miles", "Avg Distance (mi)"),
    ("trips_meeting_target", "Trips 12h+"),
    ("trips_under_target", "Under 12h"),
]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _live_probe_enabled() -> bool:
    return _env_bool("FLEETPULSE_DASHBOARD_VALIDATION_LIVE_PROBE", False)


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(int(os.getenv(name, str(default))), minimum)
    except ValueError:
        return default


def _geotab_json_rpc_readiness() -> tuple[str, str, list[str]]:
    required = ["GEOTAB_DATABASE", "GEOTAB_USERNAME", "GEOTAB_PASSWORD"]
    missing = [name for name in required if not os.getenv(name, "").strip()]
    if missing:
        return "failed", f"Missing Geotab config: {', '.join(missing)}.", missing
    return "pending", "Geotab config is present; live row probe is disabled until connector auth is clean.", required


def _geotab_odata_readiness() -> tuple[str, str, list[str]]:
    required = ["GEOTAB_DATABASE", "GEOTAB_USERNAME", "GEOTAB_PASSWORD"]
    missing = [name for name in required if not os.getenv(name, "").strip()]
    database = os.getenv("GEOTAB_DATABASE", "").strip().strip("/")
    username = os.getenv("GEOTAB_USERNAME", "").strip()
    if missing:
        return "failed", f"Missing Data Connector config: {', '.join(missing)}.", missing
    basic_auth_username = username if "/" in username else f"{database}/{username}"
    if "/" not in basic_auth_username:
        return "failed", "Data Connector Basic auth username could not be derived from GEOTAB_DATABASE and GEOTAB_USERNAME.", required
    return "pending", "Data Connector credentials are configured; live OData row probe must pass before Verified.", required


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_check_iso(minutes: int = 60) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _item(
    key: str,
    label: str,
    status: str,
    *,
    source_authority: str,
    message: str,
    row_count: int | None = None,
    metrics: list[str] | None = None,
    required_config: list[str] | None = None,
    checked_at: str | None = None,
    blocked_by: str | None = None,
    next_check: str | None = None,
    contract: dict[str, Any] | None = None,
) -> ValidationItem:
    return {
        "blocked_by": blocked_by,
        "checked_at": checked_at or _now_iso(),
        "contract": contract or {},
        "key": key,
        "label": label,
        "message": message,
        "metrics": metrics or [],
        "next_check": next_check,
        "projection_mode": "read_only",
        "required_config": required_config or [],
        "row_count": row_count,
        "source_authority": source_authority,
        "status": status,
        "verified": status == "verified",
    }


def _copy_metric(item: ValidationItem, key: str, label: str) -> ValidationItem:
    copied = dict(item)
    copied["key"] = key
    copied["label"] = label
    copied["metrics"] = [key]
    return copied


def _has_positive_number(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _schema_list_ok(rows: Any, required_attrs: tuple[str, ...]) -> bool:
    if not isinstance(rows, list):
        return False
    return all(all(hasattr(row, attr) for attr in required_attrs) for row in rows)


def _data_contract(name: str, grain: str, window: str) -> dict[str, Any]:
    return {
        "name": name,
        "stages": {
            "schema_ready": "query_ok && schema_ok && rowcount == 0",
            "data_ready": "query_ok && schema_ok && rowcount > 0",
        },
        "grain": grain,
        "window": window,
    }


def _audit_contract(name: str, required_ok: int, within_minutes: int) -> dict[str, Any]:
    return {
        "name": name,
        "rule": "last_n_audit_records_ok",
        "required_ok": required_ok,
        "within_minutes": within_minutes,
    }


def _last_seen_suffix(probe_name: str) -> str:
    try:
        last_seen = last_seen_row_at(probe_name)
    except Exception:
        last_seen = None
    return f" Last source row was seen at {last_seen}." if last_seen else ""


def _record_probe_safe(
    probe_name: str,
    status: str,
    *,
    reason: str,
    rowcount: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        record_probe(probe_name, status, reason=reason, rowcount=rowcount, metadata=metadata)
    except Exception:
        return


def _audit_contract_ok_safe(probe_name: str, *, required_ok: int, within_minutes: int) -> tuple[bool, int]:
    try:
        return audit_contract_ok(probe_name, required_ok=required_ok, within_minutes=within_minutes)
    except Exception:
        return False, 0


def _validate_k1l_final_cpm() -> tuple[ValidationItem, dict[str, ValidationItem]]:
    snapshot = get_k1l_operating_kpi_snapshot()
    status = str(snapshot.get("status") or "")
    summary = snapshot.get("summary") or {}
    monthly = snapshot.get("monthly") or []
    cost_ready = (
        status == "configured"
        and isinstance(monthly, list)
        and len(monthly) > 0
        and _has_positive_number(summary.get("total_cost"))
        and _has_positive_number(summary.get("miles"))
        and summary.get("cost_per_mile") is not None
    )
    revenue_status = snapshot.get("revenue_source_status") if isinstance(snapshot.get("revenue_source_status"), dict) else {}
    revenue_source = str(snapshot.get("revenue_source") or "")
    rpm_ready = (
        cost_ready
        and revenue_source in {POWERBI_REVENUE_SOURCE, WAREHOUSE_SQL_REVENUE_SOURCE}
        and str(revenue_status.get("status") or "") == "healthy"
        and _has_positive_number(summary.get("revenue"))
        and summary.get("revenue_per_mile") is not None
        and summary.get("profit_per_mile") is not None
    )

    source_authority = (
        "CPM: Geotab miles + QBO/AtoB/Xcelerator cost stack; "
        "Revenue/Mile: Xcelerator CEO Power BI semantic model or Fabric Warehouse SQL"
    )
    revenue_required_config = [
        "K1L_OPERATING_COST_MONTHLY_JSON",
        (
            "FLEETPULSE_XCELERATOR_WAREHOUSE_SQL_* or "
            "FLEETPULSE_XCELERATOR_CEO_POWERBI_ACCESS_TOKEN/client credentials"
        ),
    ]

    if cost_ready and rpm_ready:
        item = _item(
            "k1l_final_cpm",
            "K1L Revenue/Mile / CPM / Profit",
            "verified",
            source_authority=source_authority,
            message="Validated CPM from monthly cost rows and revenue-per-mile/profit from Xcelerator revenue projection.",
            row_count=len(monthly),
            metrics=[
                "cost_per_mile",
                "revenue_per_mile",
                "profit_per_mile",
                "total_cost",
                "miles",
                "revenue",
                "gross_profit",
                "fleet_maintenance",
                "added_p_and_l_ops",
            ],
        )
        cost_item = _copy_metric(item, "k1l_final_cpm", "K1L Final CPM")
        revenue_item = _copy_metric(item, "k1l_revenue_per_mile", "K1L Revenue Per Mile")
        profit_item = _copy_metric(item, "k1l_profit_per_mile", "K1L Profit Per Mile")
    elif cost_ready:
        revenue_status_name = str(revenue_status.get("status") or "not_configured")
        pending_status = "pending_no_data" if revenue_status_name == "awaiting_feed" else "pending"
        item = _item(
            "k1l_final_cpm",
            "K1L Revenue/Mile / CPM / Profit",
            pending_status,
            source_authority=source_authority,
            message=(
                "CPM is configured, but revenue-per-mile/profit are not verified until "
                "Xcelerator revenue projection is healthy."
            ),
            row_count=len(monthly),
            required_config=revenue_required_config,
            blocked_by="no_rows" if pending_status == "pending_no_data" else "revenue_unverified",
            metrics=[
                "cost_per_mile",
                "revenue_per_mile",
                "profit_per_mile",
                "total_cost",
                "miles",
                "revenue",
                "gross_profit",
                "fleet_maintenance",
                "added_p_and_l_ops",
            ],
            contract={
                "cost_stack": "monthly rows with positive total_cost, miles, and cost_per_mile",
                "revenue_per_mile_stack": "Xcelerator monthly K1 Logistics Inc revenue projection with rowcount > 0",
                "revenue_source_status": revenue_status_name,
            },
        )
        cost_item = _item(
            "k1l_final_cpm",
            "K1L Final CPM",
            "verified",
            source_authority=snapshot.get("source")
            or "QBO K1 Logistics P&L + Xcelerator driver pay + AtoB fuel + Geotab miles",
            message="Validated from configured monthly cost rows with positive total cost, miles, and CPM.",
            row_count=len(monthly),
            metrics=["cost_per_mile"],
        )
        revenue_item = _copy_metric(item, "k1l_revenue_per_mile", "K1L Revenue Per Mile")
        profit_item = _copy_metric(item, "k1l_profit_per_mile", "K1L Profit Per Mile")
    elif status == "configuration_error":
        item = _item(
            "k1l_final_cpm",
            "K1L Revenue/Mile / CPM / Profit",
            "failed",
            source_authority="QBO + Xcelerator + AtoB + Geotab",
            message=str(snapshot.get("error") or "K1L operating-cost configuration could not be parsed."),
            required_config=["K1L_OPERATING_COST_MONTHLY_JSON"],
        )
        cost_item = _copy_metric(item, "k1l_final_cpm", "K1L Final CPM")
        revenue_item = _copy_metric(item, "k1l_revenue_per_mile", "K1L Revenue Per Mile")
        profit_item = _copy_metric(item, "k1l_profit_per_mile", "K1L Profit Per Mile")
    else:
        item = _item(
            "k1l_final_cpm",
            "K1L Revenue/Mile / CPM / Profit",
            "pending",
            source_authority="QBO + Xcelerator + AtoB + Geotab",
            message="K1L operating-cost monthly rows are not configured, so CPM is not verified.",
            required_config=["K1L_OPERATING_COST_MONTHLY_JSON"],
        )
        cost_item = _copy_metric(item, "k1l_final_cpm", "K1L Final CPM")
        revenue_item = _copy_metric(item, "k1l_revenue_per_mile", "K1L Revenue Per Mile")
        profit_item = _copy_metric(item, "k1l_profit_per_mile", "K1L Profit Per Mile")

    metrics = {
        "k1l_final_cpm": cost_item,
        "k1l_revenue_per_mile": revenue_item,
        "k1l_profit_per_mile": profit_item,
        "k1l_total_cost": _copy_metric(cost_item, "k1l_total_cost", "K1L Total Cost"),
        "k1l_miles": _copy_metric(cost_item, "k1l_miles", "K1L Miles"),
        "k1l_revenue": _copy_metric(revenue_item, "k1l_revenue", "K1L Revenue"),
        "k1l_gross_profit": _copy_metric(profit_item, "k1l_gross_profit", "K1L Gross Profit"),
        "k1l_fleet_maintenance": _copy_metric(cost_item, "k1l_fleet_maintenance", "K1L Fleet Maintenance"),
        "k1l_added_ops": _copy_metric(cost_item, "k1l_added_ops", "K1L Added P&L Ops"),
    }
    return item, metrics


def _validate_fleet_overview() -> tuple[ValidationItem, dict[str, ValidationItem]]:
    if not _live_probe_enabled():
        status, message, required_config = _geotab_json_rpc_readiness()
        item = _item(
            "fleet_overview",
            "Fleet Overview KPI Cards",
            status,
            source_authority="K1 Logistics Inc / Geotab",
            message=message,
            metrics=[key for key, _label in OVERVIEW_METRICS],
            required_config=required_config,
        )
        metrics = {key: _copy_metric(item, key, label) for key, label in OVERVIEW_METRICS}
        return item, metrics

    try:
        overview = get_fleet_overview()
        payload = overview.model_dump() if hasattr(overview, "model_dump") else dict(overview)
        source_mode = str(payload.get("source_mode") or "")
        row_count = int(payload.get("scoped_device_count") or payload.get("total_vehicles") or 0)
        raw_status_count = int(payload.get("raw_status_count") or 0)
        stale_status_count = int(payload.get("stale_status_count") or 0)

        if source_mode in {"live_filtered", "cached_live_filtered"} and row_count > 0 and raw_status_count > 0:
            status = "verified"
            message = (
                f"Geotab fleet overview returned {row_count} scoped vehicles and "
                f"{raw_status_count} status rows."
            )
        elif source_mode.startswith("cached_after") or source_mode == "cached_refresh_in_progress":
            status = "stale"
            message = f"Using cached Geotab overview while refresh is degraded ({source_mode})."
        elif row_count > 0:
            status = "pending"
            message = f"Geotab overview returned scoped vehicles but status freshness is incomplete ({source_mode})."
        else:
            status = "failed"
            message = f"Geotab overview did not return scoped live fleet rows ({source_mode or 'unknown'})."

        item = _item(
            "fleet_overview",
            "Fleet Overview KPI Cards",
            status,
            source_authority="K1 Logistics Inc / Geotab",
            message=message,
            row_count=row_count,
            metrics=[key for key, _label in OVERVIEW_METRICS],
            required_config=["GEOTAB_DATABASE", "GEOTAB_USERNAME", "GEOTAB_PASSWORD"],
        )
        item["stale_status_count"] = stale_status_count
    except Exception as exc:
        item = _item(
            "fleet_overview",
            "Fleet Overview KPI Cards",
            "failed",
            source_authority="K1 Logistics Inc / Geotab",
            message=f"Geotab overview validation failed: {exc}",
            required_config=["GEOTAB_DATABASE", "GEOTAB_USERNAME", "GEOTAB_PASSWORD"],
        )

    metrics = {key: _copy_metric(item, key, label) for key, label in OVERVIEW_METRICS}
    return item, metrics


def _validate_vehicle_surfaces() -> dict[str, ValidationItem]:
    if not _live_probe_enabled():
        status, message, required_config = _geotab_json_rpc_readiness()
        return {
            "fleet_map": _item(
                "fleet_map",
                "Fleet Map",
                status,
                source_authority="K1 Logistics Inc / Geotab",
                message=message,
                metrics=["vehicle_position", "vehicle_status", "trailer_reference"],
                required_config=required_config,
            ),
            "vehicles": _item(
                "vehicles",
                "Vehicle List",
                status,
                source_authority="K1 Logistics Inc / Geotab",
                message=message,
                metrics=["vehicle_name", "status", "last_contact"],
                required_config=required_config,
            ),
            "locations": _item(
                "locations",
                "Location Cards",
                status,
                source_authority="K1 Logistics Inc / Geotab",
                message=message,
                metrics=["vehicle_count", "active", "safety_score"],
                required_config=required_config,
            ),
        }

    try:
        vehicles = get_vehicles()
        locations = get_location_stats()
        vehicle_count = len(vehicles)
        vehicles_status = "verified" if vehicle_count > 0 else "pending"
        vehicles_message = (
            f"Validated {vehicle_count} Geotab vehicle rows."
            if vehicle_count > 0
            else "No Geotab vehicle rows returned; vehicle list and map are not verified."
        )
        location_count = len(locations)
        return {
            "fleet_map": _item(
                "fleet_map",
                "Fleet Map",
                vehicles_status,
                source_authority="K1 Logistics Inc / Geotab",
                message=vehicles_message,
                row_count=vehicle_count,
                metrics=["vehicle_position", "vehicle_status", "trailer_reference"],
            ),
            "vehicles": _item(
                "vehicles",
                "Vehicle List",
                vehicles_status,
                source_authority="K1 Logistics Inc / Geotab",
                message=vehicles_message,
                row_count=vehicle_count,
                metrics=["vehicle_name", "status", "last_contact"],
            ),
            "locations": _item(
                "locations",
                "Location Cards",
                "verified" if location_count > 0 and vehicle_count > 0 else "pending",
                source_authority="K1 Logistics Inc / Geotab",
                message=(
                    f"Validated {location_count} configured K1 locations against Geotab vehicle rows."
                    if location_count > 0 and vehicle_count > 0
                    else "Location cards are configured, but live vehicle rows are not verified."
                ),
                row_count=location_count,
                metrics=["vehicle_count", "active", "safety_score"],
            ),
        }
    except Exception as exc:
        failed = _item(
            "vehicles",
            "Vehicle List",
            "failed",
            source_authority="K1 Logistics Inc / Geotab",
            message=f"Vehicle validation failed: {exc}",
            required_config=["GEOTAB_DATABASE", "GEOTAB_USERNAME", "GEOTAB_PASSWORD"],
        )
        return {
            "fleet_map": _copy_metric(failed, "fleet_map", "Fleet Map"),
            "vehicles": failed,
            "locations": _copy_metric(failed, "locations", "Location Cards"),
        }


def _validate_safety_surfaces() -> dict[str, ValidationItem]:
    contract = _data_contract("geotab_safety_rows", "7_day_exception_event_rollup", "last_7_days")
    if os.getenv("FLEETPULSE_SAFETY_DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}:
        pending = _item(
            "safety_scorecard",
            "Safety Scorecard",
            "pending_no_data",
            source_authority="K1 Logistics Inc / Geotab",
            message="Safety demo mode is enabled, so safety and leaderboard sections are not verified.",
            blocked_by="no_data",
            next_check=_next_check_iso(),
            contract=contract,
            required_config=["FLEETPULSE_SAFETY_DEMO_MODE=false"],
        )
        return {
            "safety_scorecard": pending,
            "driver_leaderboard": _copy_metric(pending, "driver_leaderboard", "Driver Leaderboard"),
        }

    if not _live_probe_enabled():
        status, message, required_config = _geotab_json_rpc_readiness()
        safety = _item(
            "safety_scorecard",
            "Safety Scorecard",
            status,
            source_authority="K1 Logistics Inc / Geotab",
            message=message,
            metrics=["safety_score", "event_count", "trend"],
            contract=contract,
            required_config=required_config,
        )
        return {
            "safety_scorecard": safety,
            "driver_leaderboard": _copy_metric(safety, "driver_leaderboard", "Driver Leaderboard"),
        }

    try:
        scores = get_safety_scores(days=7)
        schema_ok = _schema_list_ok(scores, ("vehicle_id", "score", "event_count"))
        row_count = len(scores) if schema_ok else 0
        _record_probe_safe(
            "geotab_safety",
            "OK" if schema_ok else "FAIL",
            reason="schema_ok" if schema_ok else "schema_invalid",
            rowcount=row_count,
            metadata={"window_days": 7},
        )
        status = "verified" if row_count > 0 else "pending_no_data"
        message = (
            f"Validated {row_count} Geotab safety score rows from exception-event rules."
            if row_count > 0
            else f"Safety query returned 200/schema OK but no Geotab safety rows; section is waiting for source rows.{_last_seen_suffix('geotab_safety')}"
        )
        safety = _item(
            "safety_scorecard",
            "Safety Scorecard",
            status,
            source_authority="K1 Logistics Inc / Geotab",
            message=message,
            row_count=row_count,
            metrics=["safety_score", "event_count", "trend"],
            blocked_by=None if row_count > 0 else "no_rows",
            next_check=None if row_count > 0 else _next_check_iso(_env_int("FLEETPULSE_SAFETY_SYNC_CADENCE_MINUTES", 60)),
            contract=contract,
        )
        leaderboard = _item(
            "driver_leaderboard",
            "Driver Leaderboard",
            status,
            source_authority="K1 Logistics Inc / Geotab",
            message=(
                "Driver leaderboard is validated from safety rows."
                if row_count > 0
                else f"Driver leaderboard query path is OK, but it is waiting for Geotab safety rows.{_last_seen_suffix('geotab_safety')}"
            ),
            row_count=row_count,
            metrics=["rank", "points", "safety_score"],
            blocked_by=None if row_count > 0 else "no_rows",
            next_check=None if row_count > 0 else _next_check_iso(_env_int("FLEETPULSE_SAFETY_SYNC_CADENCE_MINUTES", 60)),
            contract=contract,
        )
        return {"safety_scorecard": safety, "driver_leaderboard": leaderboard}
    except Exception as exc:
        _record_probe_safe("geotab_safety", "FAIL", reason=type(exc).__name__, rowcount=None)
        failed = _item(
            "safety_scorecard",
            "Safety Scorecard",
            "failed",
            source_authority="K1 Logistics Inc / Geotab",
            message=f"Safety validation failed: {exc}",
            required_config=["GEOTAB_DATABASE", "GEOTAB_USERNAME", "GEOTAB_PASSWORD"],
        )
        return {
            "safety_scorecard": failed,
            "driver_leaderboard": _copy_metric(failed, "driver_leaderboard", "Driver Leaderboard"),
        }


def _validate_alert_surfaces() -> dict[str, ValidationItem]:
    alert_contract = _data_contract("geotab_alert_rows", "exception_event_alert", "last_24_hours")
    monitor_required_ok = _env_int("FLEETPULSE_AGENTIC_MONITOR_AUDIT_REQUIRED_OK", 3)
    monitor_window = _env_int("FLEETPULSE_AGENTIC_MONITOR_AUDIT_WINDOW_MINUTES", 15)
    monitor_contract = _audit_contract("agentic_monitor", monitor_required_ok, monitor_window)
    if not _live_probe_enabled():
        status, message, required_config = _geotab_json_rpc_readiness()
        alerts = _item(
            "alerts",
            "Alert Feed",
            status,
            source_authority="K1 Logistics Inc / Geotab",
            message=message,
            metrics=["severity", "alert_type", "timestamp"],
            contract=alert_contract,
            required_config=required_config,
        )
        monitor = _item(
            "agentic_monitor",
            "Agentic Monitor",
            "pending" if status != "failed" else "failed",
            source_authority="K1 Logistics Inc / Geotab",
            message=(
                "Monitor output needs live Geotab probes and durable audit rows before Verified."
                if status != "failed"
                else message
            ),
            metrics=["monitor_status", "alert_history"],
            contract=monitor_contract,
            required_config=required_config,
        )
        return {"alerts": alerts, "agentic_monitor": monitor}

    try:
        alerts = get_recent_alerts(hours=24)
        schema_ok = _schema_list_ok(alerts, ("id", "severity", "timestamp"))
        alert_count = len(alerts) if schema_ok else 0
        _record_probe_safe(
            "geotab_alerts",
            "OK" if schema_ok else "FAIL",
            reason="schema_ok" if schema_ok else "schema_invalid",
            rowcount=alert_count,
            metadata={"window_hours": 24},
        )
        zero_event_verified = (
            alert_count == 0
            and schema_ok
            and _env_bool("FLEETPULSE_ALERT_ZERO_EVENT_AUDIT_ENABLED", False)
        )
        if alert_count > 0:
            status = "verified"
            message = f"Validated {alert_count} recent Geotab alert rows."
        elif zero_event_verified:
            status = "verified"
            message = "Alert query returned 200/schema OK with zero rows and zero-event audit mode is enabled for this 24h window."
        else:
            status = "pending_no_data"
            message = f"Alert query returned 200/schema OK with no recent alert rows; section is waiting for alert rows or a zero-event audit.{_last_seen_suffix('geotab_alerts')}"

        monitor_status = get_monitor_status()
        monitor_ok = bool(monitor_status.get("running"))
        _record_probe_safe(
            "agentic_monitor",
            "OK" if monitor_ok else "FAIL",
            reason="running" if monitor_ok else "not_running",
            rowcount=int(monitor_status.get("total_alerts") or 0),
            metadata={"patterns_present": bool(monitor_status.get("patterns"))},
        )
        monitor_verified, monitor_ok_count = _audit_contract_ok_safe(
            "agentic_monitor",
            required_ok=monitor_required_ok,
            within_minutes=monitor_window,
        )
        monitor_validation_status = "verified" if monitor_verified else "pending_no_audit"
        monitor_message = (
            f"Agentic Monitor has {monitor_ok_count} consecutive OK audit rows inside {monitor_window} minutes."
            if monitor_verified
            else f"Agentic Monitor needs {monitor_required_ok} OK audit rows inside {monitor_window} minutes; current OK count is {monitor_ok_count}."
        )
        return {
            "alerts": _item(
                "alerts",
                "Alert Feed",
                status,
                source_authority="K1 Logistics Inc / Geotab",
                message=message,
                row_count=alert_count,
                metrics=["severity", "alert_type", "timestamp"],
                blocked_by=None if alert_count > 0 or zero_event_verified else "no_rows",
                next_check=None if alert_count > 0 or zero_event_verified else _next_check_iso(_env_int("FLEETPULSE_ALERT_SYNC_CADENCE_MINUTES", 60)),
                contract=alert_contract,
            ),
            "agentic_monitor": _item(
                "agentic_monitor",
                "Agentic Monitor",
                monitor_validation_status,
                source_authority="K1 Logistics Inc / Geotab",
                message=monitor_message,
                metrics=["monitor_status", "alert_history"],
                row_count=monitor_ok_count,
                blocked_by=None if monitor_verified else "no_audit",
                next_check=None if monitor_verified else _next_check_iso(_env_int("FLEETPULSE_AGENTIC_MONITOR_AUDIT_WRITE_CADENCE_MINUTES", 5)),
                contract=monitor_contract,
            ),
        }
    except Exception as exc:
        _record_probe_safe("geotab_alerts", "FAIL", reason=type(exc).__name__, rowcount=None)
        failed = _item(
            "alerts",
            "Alert Feed",
            "failed",
            source_authority="K1 Logistics Inc / Geotab",
            message=f"Alert validation failed: {exc}",
            required_config=["GEOTAB_DATABASE", "GEOTAB_USERNAME", "GEOTAB_PASSWORD"],
        )
        return {
            "alerts": failed,
            "agentic_monitor": _copy_metric(failed, "agentic_monitor", "Agentic Monitor"),
        }


def _probe_data_connector_row_count() -> int:
    from routers import data_connector

    rows = asyncio.run(data_connector._odata_get("VehicleKpi_Daily", search="last_1_day", top=1))
    return len(rows)


def _validate_static_or_config_surfaces() -> dict[str, ValidationItem]:
    os_config = OperatingSystemRuntimeConfig.from_env()
    if os_config.api_key_required and not os_config.api_key_configured:
        operating_status = "failed"
        operating_message = "Operating System endpoints require an API key, but none is configured."
    else:
        operating_status = "verified"
        operating_message = "Operating System read-only contract configuration is accessible."

    data_connector_status, dc_message, dc_required_config = _geotab_odata_readiness()
    data_connector_row_count: int | None = None

    if data_connector_status != "failed" and _live_probe_enabled():
        try:
            data_connector_row_count = _probe_data_connector_row_count()
            if data_connector_row_count > 0:
                data_connector_status = "verified"
                dc_message = "Validated Geotab Data Connector OData row access with the effective Basic auth username."
            else:
                data_connector_status = "pending"
                dc_message = "Geotab Data Connector authenticated, but VehicleKpi_Daily returned no recent rows."
        except Exception as exc:
            data_connector_status = "failed"
            dc_message = f"Data Connector validation failed: {exc}"

    return {
        "fleet_analytics": _item(
            "fleet_analytics",
            "Fleet Analytics",
            "pending_no_audit",
            source_authority="K1 Logistics Inc / Geotab + Power BI",
            message="Trend charts remain unverified until the panel is backed by live daily/weekly trend rows and a gap-check audit contract.",
            metrics=["trip_trend", "utilization_trend"],
            blocked_by="no_audit",
            next_check=_next_check_iso(_env_int("FLEETPULSE_FLEET_ANALYTICS_AUDIT_WRITE_CADENCE_MINUTES", 60)),
            contract={
                "name": "fleet_analytics_trend_contract",
                "expected_grain": os.getenv("FLEETPULSE_FLEET_ANALYTICS_EXPECTED_GRAIN", "daily"),
                "minimum_periods": _env_int("FLEETPULSE_FLEET_ANALYTICS_MIN_PERIODS", 7),
                "window_days": _env_int("FLEETPULSE_FLEET_ANALYTICS_WINDOW_DAYS", 14),
                "allowed_gap_days": _env_int("FLEETPULSE_FLEET_ANALYTICS_ALLOWED_GAP_DAYS", 1),
                "rule": "live_trend_rows_present_and_gap_checked",
            },
        ),
        "data_connector": _item(
            "data_connector",
            "Data Connector",
            data_connector_status,
            source_authority="K1 Logistics Inc / Geotab OData",
            message=dc_message,
            row_count=data_connector_row_count,
            required_config=dc_required_config,
        ),
        "operating_system": _item(
            "operating_system",
            "K1 Seat-Based Operating System",
            operating_status,
            source_authority="SharePoint contract + FleetPulse read-only config",
            message=operating_message,
            required_config=["FLEETPULSE_OPERATING_SYSTEM_API_KEY"],
        ),
    }


def _validate_driver_workforce_surface() -> ValidationItem:
    try:
        payload = get_driver_workforce_dataset()
        validation = payload.get("validation") or {}
        status = str(validation.get("status") or "pending")
        return _item(
            "driver_workforce",
            "Driver Workforce Route Windows",
            status,
            source_authority="Xcelerator route tickets + Geotab activity",
            message=str(
                validation.get("message")
                or "Xcelerator route tickets + Geotab activity"
            ),
            row_count=validation.get("row_count"),
            metrics=[
                "scheduled_today",
                "working_now",
                "late_start",
                "near_limit",
                "overdue",
                "avg_time_worked_minutes",
            ],
            required_config=[
                "FLEETPULSE_XCELERATOR_EVENT_STATE_PATH",
                "GEOTAB_DATABASE",
                "GEOTAB_USERNAME",
                "GEOTAB_PASSWORD",
            ],
            blocked_by=None if status == "verified" else validation.get("state"),
            next_check=None if status == "verified" else _next_check_iso(),
            contract={
                "name": "driver_workforce_route_windows",
                "planned_authority": "K1 Group LLC / Xcelerator",
                "actual_authority": "K1 Logistics Inc / Geotab",
                "rule": "route_ticket_window_overlap_joined_to_geotab_activity",
            },
        )
    except Exception as exc:
        return _item(
            "driver_workforce",
            "Driver Workforce Route Windows",
            "failed",
            source_authority="Xcelerator route tickets + Geotab activity",
            message=f"Driver workforce route-window validation failed: {exc}",
            required_config=[
                "FLEETPULSE_XCELERATOR_EVENT_STATE_PATH",
                "GEOTAB_DATABASE",
                "GEOTAB_USERNAME",
                "GEOTAB_PASSWORD",
            ],
        )


def get_dashboard_validation_snapshot() -> dict[str, Any]:
    sections: dict[str, ValidationItem] = {}
    metrics: dict[str, ValidationItem] = {}

    k1l, k1l_metrics = _validate_k1l_final_cpm()
    overview, overview_metrics = _validate_fleet_overview()
    sections[k1l["key"]] = k1l
    sections[overview["key"]] = overview
    metrics.update(k1l_metrics)
    metrics.update(overview_metrics)
    sections.update(_validate_vehicle_surfaces())
    driver_workforce = _validate_driver_workforce_surface()
    sections[driver_workforce["key"]] = driver_workforce
    sections.update(_validate_safety_surfaces())
    sections.update(_validate_alert_surfaces())
    sections.update(_validate_static_or_config_surfaces())

    summary = {status: 0 for status in ("verified", "pending", "pending_no_data", "pending_no_audit", "stale", "failed")}
    for item in sections.values():
        status = str(item.get("status") or "pending")
        summary[status] = summary.get(status, 0) + 1

    metric_summary = {status: 0 for status in ("verified", "pending", "pending_no_data", "pending_no_audit", "stale", "failed")}
    for item in metrics.values():
        status = str(item.get("status") or "pending")
        metric_summary[status] = metric_summary.get(status, 0) + 1

    pending_ledger = [
        {
            "panel_name": item.get("label"),
            "key": item.get("key"),
            "status": item.get("status"),
            "blocked_by": item.get("blocked_by") or "validation_not_complete",
            "contract": item.get("contract") or {},
            "next_check": item.get("next_check") or _next_check_iso(),
            "message": item.get("message"),
        }
        for item in sections.values()
        if str(item.get("status") or "").startswith("pending")
    ]

    return {
        "generated_at": _now_iso(),
        "projection_mode": "read_only",
        "sections": sections,
        "metrics": metrics,
        "pending_ledger": pending_ledger,
        "summary": summary,
        "metric_summary": metric_summary,
    }
