"""Tests for FleetPulse Power BI connector endpoints."""

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

    class _FakeAPI:  # noqa: D401
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
from routers import powerbi  # noqa: E402


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr(
        powerbi,
        "get_fleet_overview",
        lambda: FleetOverview(total_vehicles=2, active=1, parked=1, total_trips_today=3),
    )
    monkeypatch.setattr(
        powerbi,
        "get_location_stats",
        lambda: [
            LocationStats(
                name="Fort Worth Yard",
                address="4200 Gravel Dr",
                latitude=32.8012,
                longitude=-97.2197,
                vehicle_count=2,
                active=1,
            )
        ],
    )
    monkeypatch.setattr(
        powerbi,
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
        powerbi,
        "get_safety_scores",
        lambda days=7: [
            VehicleSafetyScore(
                vehicle_id="b1",
                vehicle_name="Truck 1",
                score=91.0,
                breakdown=SafetyBreakdown(speeding=1, harsh_braking=1),
                trend=TrendDirection.STABLE,
                event_count=2,
            )
        ],
    )

    app = FastAPI()
    app.include_router(powerbi.router, prefix="/api/powerbi")
    return TestClient(app)


def test_powerbi_overview_connection(monkeypatch):
    response = _client(monkeypatch).get("/api/powerbi/overview")

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["connection_name"] == "fleetpulse_overview"
    assert rows[0]["projection_mode"] == "read_only"
    assert rows[0]["source_authority"] == "Geotab"
    assert rows[0]["total_vehicles"] == 2


def test_powerbi_locations_connection(monkeypatch):
    response = _client(monkeypatch).get("/api/powerbi/locations")

    assert response.status_code == 200
    rows = response.json()
    assert rows[0]["connection_name"] == "fleetpulse_locations"
    assert rows[0]["name"] == "Fort Worth Yard"


def test_powerbi_vehicles_connection_flattens_position(monkeypatch):
    response = _client(monkeypatch).get("/api/powerbi/vehicles")

    assert response.status_code == 200
    rows = response.json()
    assert rows[0]["connection_name"] == "fleetpulse_vehicles"
    assert rows[0]["latitude"] == 32.8
    assert rows[0]["longitude"] == -97.2
    assert "position" not in rows[0]


def test_powerbi_safety_scores_connection_flattens_breakdown(monkeypatch):
    response = _client(monkeypatch).get("/api/powerbi/safety-scores?days=14")

    assert response.status_code == 200
    rows = response.json()
    assert rows[0]["connection_name"] == "fleetpulse_safety_scores"
    assert rows[0]["period_days"] == 14
    assert rows[0]["speeding_events"] == 1
    assert rows[0]["harsh_braking_events"] == 1
    assert "breakdown" not in rows[0]


def test_powerbi_fleetpulse_snapshot_connection(monkeypatch):
    response = _client(monkeypatch).get("/api/powerbi/fleetpulse-snapshot?days=14")

    assert response.status_code == 200
    payload = response.json()
    assert payload["connection_name"] == "fleetpulse_snapshot"
    assert payload["projection_mode"] == "read_only"
    assert payload["row_counts"] == {
        "overview": 1,
        "locations": 1,
        "vehicles": 1,
        "safety_scores": 1,
    }
    assert payload["tables"]["vehicles"][0]["id"] == "b1"


def test_powerbi_dashboard_preview_serves_html(monkeypatch):
    response = _client(monkeypatch).get("/api/powerbi/dashboard-preview")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "FleetPulse Power BI Dashboard Preview" in response.text
