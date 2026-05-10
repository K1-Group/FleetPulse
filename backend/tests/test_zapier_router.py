"""Tests for FleetPulse Zapier integration endpoints."""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Make backend/ importable regardless of how pytest is invoked.
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Stub mygeotab so service modules import without the SDK installed.
if "mygeotab" not in sys.modules:
    fake = types.ModuleType("mygeotab")

    class _FakeAPI:
        def __init__(self, *a, **kw):
            pass

        def authenticate(self):
            pass

        def get(self, *a, **kw):
            return []

    fake.API = _FakeAPI
    sys.modules["mygeotab"] = fake

from models import (  # noqa: E402
    FleetOverview,
    LocationStats,
    SafetyBreakdown,
    TrendDirection,
    Vehicle,
    VehiclePosition,
    VehicleSafetyScore,
    VehicleStatus,
)
from routers import zapier  # noqa: E402


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr(
        zapier,
        "get_fleet_overview",
        lambda: FleetOverview(total_vehicles=3, active=2, parked=1, total_trips_today=4),
    )
    monkeypatch.setattr(
        zapier,
        "get_location_stats",
        lambda: [
            LocationStats(
                name="Fort Worth Yard",
                address="4200 Gravel Dr",
                latitude=32.8012,
                longitude=-97.2197,
                vehicle_count=3,
                active=2,
            )
        ],
    )
    monkeypatch.setattr(
        zapier,
        "get_vehicles",
        lambda: [
            Vehicle(
                id="b1",
                name="Truck 1",
                status=VehicleStatus.ACTIVE,
                position=VehiclePosition(latitude=32.8, longitude=-97.2, bearing=180, speed=55),
                location_name="Fort Worth Yard",
                last_contact=datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc),
            )
        ],
    )
    monkeypatch.setattr(
        zapier,
        "get_safety_scores",
        lambda days=7: [
            VehicleSafetyScore(
                vehicle_id="b1",
                vehicle_name="Truck 1",
                score=82.0,
                breakdown=SafetyBreakdown(speeding=3, harsh_braking=1),
                trend=TrendDirection.DECLINING,
                event_count=4,
            ),
            VehicleSafetyScore(
                vehicle_id="b2",
                vehicle_name="Truck 2",
                score=98.0,
                event_count=0,
            ),
        ],
    )

    app = FastAPI()
    app.include_router(zapier.router, prefix="/api/zapier")
    return TestClient(app)


def test_zapier_status_does_not_expose_secret_values(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_ZAPIER_ENABLED", "true")
    monkeypatch.setenv("FLEETPULSE_ZAPIER_WEBHOOK_URL", "https://hooks.zapier.com/hooks/catch/test")
    monkeypatch.setenv("FLEETPULSE_ZAPIER_API_KEY", "super-secret")
    monkeypatch.setenv("FLEETPULSE_ZAPIER_SHARED_SECRET", "signing-secret")

    response = _client(monkeypatch).get("/api/zapier/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is True
    assert payload["webhook_configured"] is True
    assert payload["api_key_required"] is True
    assert payload["signing_enabled"] is True
    assert "super-secret" not in response.text
    assert "signing-secret" not in response.text


def test_fleet_snapshot_trigger_returns_zapier_list(monkeypatch):
    response = _client(monkeypatch).get("/api/zapier/triggers/fleet-snapshot?days=14")

    assert response.status_code == 200
    rows = response.json()
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "fleetpulse.snapshot"
    assert rows[0]["source_authority"] == "Geotab"
    assert rows[0]["projection_mode"] == "read_only"
    assert rows[0]["period_days"] == 14
    assert rows[0]["row_counts"] == {"locations": 1, "vehicles": 1, "safety_scores": 2}
    assert rows[0]["top_risk_vehicle_name"] == "Truck 1"


def test_risk_vehicles_trigger_filters_threshold(monkeypatch):
    response = _client(monkeypatch).get(
        "/api/zapier/triggers/risk-vehicles?days=7&max_score=85&min_events=1"
    )

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "fleetpulse.risk_vehicle"
    assert rows[0]["vehicle_name"] == "Truck 1"
    assert rows[0]["score"] == 82.0
    assert rows[0]["speeding_events"] == 3


def test_push_snapshot_disabled_by_default(monkeypatch):
    response = _client(monkeypatch).post("/api/zapier/actions/push-snapshot")

    assert response.status_code == 409
    assert response.json()["detail"] == "zapier_push_disabled"


def test_push_snapshot_requires_api_key_when_configured(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_ZAPIER_ENABLED", "true")
    monkeypatch.setenv("FLEETPULSE_ZAPIER_API_KEY", "expected")
    monkeypatch.setenv("FLEETPULSE_ZAPIER_WEBHOOK_URL", "https://hooks.zapier.com/hooks/catch/test")

    response = _client(monkeypatch).post("/api/zapier/actions/push-snapshot")

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_zapier_api_key"


def test_push_snapshot_sends_to_configured_webhook(monkeypatch):
    sent: list[dict] = []

    async def fake_post_webhook(payload):
        sent.append(payload)
        return {"status": "sent", "zapier_status_code": 200, "payload_id": payload["id"]}

    monkeypatch.setenv("FLEETPULSE_ZAPIER_ENABLED", "true")
    monkeypatch.setenv("FLEETPULSE_ZAPIER_API_KEY", "expected")
    monkeypatch.setenv("FLEETPULSE_ZAPIER_WEBHOOK_URL", "https://hooks.zapier.com/hooks/catch/test")
    monkeypatch.setattr(zapier, "_post_webhook", fake_post_webhook)

    response = _client(monkeypatch).post(
        "/api/zapier/actions/push-snapshot",
        headers={"X-FleetPulse-Zapier-Key": "expected"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    assert sent[0]["event_type"] == "fleetpulse.snapshot"


def test_payload_signature_validates_and_rejects_tampering(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_ZAPIER_SHARED_SECRET", "signing-secret")
    payload = {
        "id": "fleetpulse-snapshot-test",
        "event_type": "fleetpulse.snapshot",
        "source_system": "FleetPulse",
        "source_authority": "Geotab",
        "projection_mode": "read_only",
    }

    signed = zapier._attach_payload_signature(payload)

    assert signed["signature_algorithm"] == zapier.SIGNATURE_ALGORITHM
    assert signed["payload_signature"].startswith("sha256=")
    assert zapier._verify_payload_signature(signed)
    assert "payload_signature" not in payload

    tampered = {**signed, "source_authority": "Manual"}
    assert not zapier._verify_payload_signature(tampered)


def test_verify_snapshot_action_returns_valid_for_signed_payload(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_ZAPIER_SHARED_SECRET", "signing-secret")
    payload = zapier._attach_payload_signature(
        {
            "id": "fleetpulse-snapshot-test",
            "event_type": "fleetpulse.snapshot",
            "source_system": "FleetPulse",
            "source_authority": "Geotab",
            "projection_mode": "read_only",
        }
    )

    response = _client(monkeypatch).post(
        "/api/zapier/actions/verify-snapshot",
        json={"payload": payload},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["valid"] is True
    assert result["status"] == "ok"
    assert result["payload_id"] == "fleetpulse-snapshot-test"


def test_verify_snapshot_action_rejects_unsigned_payload(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_ZAPIER_SHARED_SECRET", "signing-secret")

    response = _client(monkeypatch).post(
        "/api/zapier/actions/verify-snapshot",
        json={
            "payload": {
                "id": "fleetpulse-snapshot-test",
                "event_type": "fleetpulse.snapshot",
                "source_system": "FleetPulse",
                "source_authority": "Geotab",
                "projection_mode": "read_only",
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert response.json()["status"] == "invalid"
