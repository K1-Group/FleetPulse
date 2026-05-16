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
    monkeypatch.setattr(
        powerbi,
        "get_lane_stability_snapshot",
        lambda days=7: {
            "period_start": "2026-05-03",
            "period_end": "2026-05-09",
            "generated_at": "2026-05-10T12:00:00+00:00",
            "feed_status": "healthy",
            "company_kpis": {
                "period_start": "2026-05-03",
                "period_end": "2026-05-09",
                "feed_status": "healthy",
                "total_revenue": 304844.11,
                "weighted_stable_cov_pct": 0.7467,
                "source_authority": "K1 Group LLC / Xcelerator",
                "projection_mode": "read_only",
            },
            "by_service": [
                {"service": "LH", "lanes": 2, "orders": 5, "weighted_stable_cov_pct": 0.8}
            ],
            "lanes": [
                {
                    "service": "LH",
                    "lane": "HDS K1",
                    "status": "At Risk",
                    "orders": 5,
                    "stable_cov_pct": 0.4,
                    "num_routes": 3,
                    "primary_route": "DFW 009",
                }
            ],
            "routes": [
                {"service": "LH", "lane": "HDS K1", "route": "DFW 009", "orders": 3}
            ],
            "daily": [
                {"date": "2026-05-09", "orders": 5, "daily_stable_cov_pct": 0.4}
            ],
            "trend": [
                {
                    "period_start": "2026-05-03",
                    "period_end": "2026-05-09",
                    "service": "LH",
                    "lane": "HDS K1",
                    "trend_type": "degrading",
                    "delta_stable_cov_pct": -0.5,
                }
            ],
            "row_counts": {"by_service": 1, "lanes": 1, "routes": 1, "daily": 1, "trend": 1},
        },
    )

    async def fake_operating_cost_snapshot(days=90, start=None, end=None):
        return {
            "period_start": start or "2026-05-03",
            "period_end": end or "2026-05-09",
            "generated_at": "2026-05-10T12:00:00+00:00",
            "complete_cost_available": True,
            "unresolved_sources": [],
            "summary": {
                "miles": 1000.0,
                "drive_hours": 50.0,
                "idle_hours": 5.0,
                "operating_hours": 55.0,
                "trips": 20,
                "fuel_cost": 625.0,
                "driver_pay": 1000.0,
                "insurance_cost": 100.0,
                "other_expense_cost": 200.0,
                "known_operating_cost": 1925.0,
                "true_operating_cost": 1925.0,
                "known_cost_per_mile": 1.925,
                "true_cost_per_mile": 1.925,
                "known_cost_per_drive_hour": 38.5,
                "true_cost_per_drive_hour": 38.5,
                "known_cost_per_operating_hour": 35.0,
                "true_cost_per_operating_hour": 35.0,
            },
            "weekly": [
                {
                    "week_start": "2026-05-04",
                    "week_end": "2026-05-09",
                    "period_start": "2026-05-04",
                    "period_end": "2026-05-09",
                    "miles": 1000.0,
                    "drive_hours": 50.0,
                    "idle_hours": 5.0,
                    "operating_hours": 55.0,
                    "trips": 20,
                    "fuel_cost": 625.0,
                    "driver_pay": 1000.0,
                    "insurance_cost": 100.0,
                    "other_expense_cost": 200.0,
                    "known_operating_cost": 1925.0,
                    "true_operating_cost": 1925.0,
                    "known_cost_per_mile": 1.925,
                    "true_cost_per_mile": 1.925,
                    "known_cost_per_drive_hour": 38.5,
                    "true_cost_per_drive_hour": 38.5,
                    "known_cost_per_operating_hour": 35.0,
                    "true_cost_per_operating_hour": 35.0,
                }
            ],
        }

    monkeypatch.setattr(
        powerbi,
        "get_operating_cost_snapshot",
        fake_operating_cost_snapshot,
    )

    async def fake_entity_margin_snapshot(days=90, start=None, end=None):
        return {
            "period_start": start or "2026-05-03",
            "period_end": end or "2026-05-09",
            "generated_at": "2026-05-10T12:00:00+00:00",
            "k1l_margin_target_pct": 0.72,
            "k1g_margin_target_pct": 0.2,
            "complete_k1l_cpm_available": True,
            "complete_k1l_true_cpm_available": True,
            "unresolved_sources": [],
            "true_cpm_unresolved_sources": [],
            "xcelerator_source_type": "powerbi_semantic_model",
            "summary": {
                "miles": 1000.0,
                "drive_hours": 50.0,
                "fuel_cost": 625.0,
                "insurance_cost": 100.0,
                "other_expense_cost": 200.0,
                "k1l_orders": 10,
                "k1l_grand_total": 3000.0,
                "k1l_driver_pay": 1000.0,
                "k1l_target_gross_margin": 2160.0,
                "k1l_actual_gross_margin_before_fuel": 2000.0,
                "k1l_actual_gross_margin_pct_before_fuel": 0.6667,
                "k1l_actual_gross_margin_after_fuel": 1375.0,
                "k1l_actual_gross_margin_pct_after_fuel": 0.4583,
                "k1l_revenue_per_mile": 3.0,
                "k1l_driver_pay_cpm": 1.0,
                "k1l_fuel_cpm": 0.625,
                "k1l_fuel_plus_driver_cpm": 1.625,
                "k1l_true_operating_cpm": 1.925,
                "k1l_true_operating_cost": 1925.0,
                "k1g_orders": 4,
                "k1g_grand_total": 1000.0,
                "k1g_driver_pay": 800.0,
                "k1g_target_gross_margin": 200.0,
                "k1g_actual_gross_margin_before_overhead": 200.0,
                "k1g_actual_gross_margin_pct_before_overhead": 0.2,
                "qbo_expenses_available": True,
            },
            "weekly": [
                {
                    "week_start": "2026-05-04",
                    "week_end": "2026-05-09",
                    "period_start": "2026-05-04",
                    "period_end": "2026-05-09",
                    "miles": 1000.0,
                    "drive_hours": 50.0,
                    "fuel_cost": 625.0,
                    "insurance_cost": 100.0,
                    "other_expense_cost": 200.0,
                    "k1l_orders": 10,
                    "k1l_grand_total": 3000.0,
                    "k1l_driver_pay": 1000.0,
                    "k1l_target_gross_margin": 2160.0,
                    "k1l_actual_gross_margin_before_fuel": 2000.0,
                    "k1l_actual_gross_margin_pct_before_fuel": 0.6667,
                    "k1l_actual_gross_margin_after_fuel": 1375.0,
                    "k1l_actual_gross_margin_pct_after_fuel": 0.4583,
                    "k1l_revenue_per_mile": 3.0,
                    "k1l_driver_pay_cpm": 1.0,
                    "k1l_fuel_cpm": 0.625,
                    "k1l_fuel_plus_driver_cpm": 1.625,
                    "k1l_true_operating_cpm": 1.925,
                    "k1l_true_operating_cost": 1925.0,
                    "k1g_orders": 4,
                    "k1g_grand_total": 1000.0,
                    "k1g_driver_pay": 800.0,
                    "k1g_target_gross_margin": 200.0,
                    "k1g_actual_gross_margin_before_overhead": 200.0,
                    "k1g_actual_gross_margin_pct_before_overhead": 0.2,
                    "qbo_expenses_available": True,
                }
            ],
        }

    monkeypatch.setattr(
        powerbi,
        "get_entity_margin_snapshot",
        fake_entity_margin_snapshot,
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


def test_powerbi_lane_stability_company_is_xcelerator_projection(monkeypatch):
    response = _client(monkeypatch).get("/api/powerbi/lane-stability/company")

    assert response.status_code == 200
    rows = response.json()
    assert rows[0]["connection_name"] == "lane_stability_company"
    assert rows[0]["source_system"] == "Xcelerator"
    assert rows[0]["source_authority"] == "K1 Group LLC / Xcelerator"
    assert rows[0]["projection_mode"] == "read_only"
    assert rows[0]["total_revenue"] == 304844.11


def test_powerbi_lane_stability_tables(monkeypatch):
    for path, expected_key in [
        ("/api/powerbi/lane-stability/by-service", "service"),
        ("/api/powerbi/lane-stability/lanes", "lane"),
        ("/api/powerbi/lane-stability/routes", "route"),
        ("/api/powerbi/lane-stability/daily", "date"),
        ("/api/powerbi/lane-stability/trend", "trend_type"),
    ]:
        response = _client(monkeypatch).get(path)

        assert response.status_code == 200
        rows = response.json()
        assert rows[0]["source_system"] == "Xcelerator"
        assert rows[0][expected_key]


def test_powerbi_lane_stability_snapshot(monkeypatch):
    response = _client(monkeypatch).get("/api/powerbi/lane-stability-snapshot")

    assert response.status_code == 200
    payload = response.json()
    assert payload["connection_name"] == "lane_stability_snapshot"
    assert payload["source_authority"] == "K1 Group LLC / Xcelerator"
    assert payload["row_counts"]["lanes"] == 1


def test_powerbi_operating_cost_tables(monkeypatch):
    client = _client(monkeypatch)
    summary = client.get("/api/powerbi/operating-cost/summary?start=2026-05-03&end=2026-05-09")
    weekly = client.get("/api/powerbi/operating-cost/weekly?start=2026-05-03&end=2026-05-09")

    assert summary.status_code == 200
    assert weekly.status_code == 200
    assert summary.json()[0]["connection_name"] == "operating_cost_summary"
    assert summary.json()[0]["source_system"] == "FleetPulse Cost Analytics"
    assert summary.json()[0]["projection_mode"] == "read_only"
    assert weekly.json()[0]["connection_name"] == "operating_cost_weekly"
    assert weekly.json()[0]["true_cost_per_mile"] == 1.925


def test_powerbi_entity_margin_tables(monkeypatch):
    client = _client(monkeypatch)
    summary = client.get("/api/powerbi/entity-margin/summary?start=2026-05-03&end=2026-05-09")
    weekly = client.get("/api/powerbi/entity-margin/weekly?start=2026-05-03&end=2026-05-09")

    assert summary.status_code == 200
    assert weekly.status_code == 200
    assert summary.json()[0]["connection_name"] == "entity_margin_summary"
    assert summary.json()[0]["source_system"] == "FleetPulse Entity Margin"
    assert summary.json()[0]["k1l_margin_target_pct"] == 0.72
    assert summary.json()[0]["k1g_margin_target_pct"] == 0.2
    assert summary.json()[0]["k1l_fuel_plus_driver_cpm"] == 1.625
    assert weekly.json()[0]["connection_name"] == "entity_margin_weekly"
    assert weekly.json()[0]["xcelerator_source_type"] == "powerbi_semantic_model"
