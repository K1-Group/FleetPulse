"""Tests for dashboard metric validation badges."""

from __future__ import annotations

import sys
import types
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

if "mygeotab" not in sys.modules:
    fake = types.ModuleType("mygeotab")

    class _FakeAPI:
        def __init__(self, *args, **kwargs):
            pass

        def authenticate(self):
            pass

        def get(self, *args, **kwargs):
            return []

    fake.API = _FakeAPI
    sys.modules["mygeotab"] = fake

from models import FleetOverview  # noqa: E402
from routers import dashboard  # noqa: E402
from services import dashboard_validation_service as validation_service  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(dashboard.router, prefix="/api/dashboard")
    return TestClient(app)


def _patch_non_kpi_sources(monkeypatch, overview: FleetOverview) -> None:
    monkeypatch.setattr(validation_service, "get_fleet_overview", lambda: overview)
    monkeypatch.setattr(validation_service, "get_vehicles", lambda: [object(), object()])
    monkeypatch.setattr(validation_service, "get_location_stats", lambda: [object(), object(), object(), object()])
    monkeypatch.setattr(
        validation_service,
        "get_safety_scores",
        lambda days=7: [types.SimpleNamespace(vehicle_id="v1", score=95, event_count=1)],
    )
    monkeypatch.setattr(validation_service, "get_recent_alerts", lambda hours=24: [])
    monkeypatch.setattr(validation_service, "get_monitor_status", lambda: {"running": True, "total_alerts": 0, "patterns": {}})
    monkeypatch.setattr(validation_service, "_probe_data_connector_row_count", lambda: 1)
    monkeypatch.setattr(validation_service, "record_probe", lambda *args, **kwargs: {})
    monkeypatch.setattr(validation_service, "last_seen_row_at", lambda probe_name: None)
    monkeypatch.setattr(validation_service, "audit_contract_ok", lambda *args, **kwargs: (False, 0))


def test_dashboard_validation_marks_only_source_backed_metrics_verified(monkeypatch):
    monkeypatch.setenv("GEOTAB_DATABASE", "k1logistics")
    monkeypatch.setenv("GEOTAB_USERNAME", "k1logistics/operator@example.com")
    monkeypatch.setenv("GEOTAB_PASSWORD", "secret")
    monkeypatch.setenv("FLEETPULSE_DASHBOARD_VALIDATION_LIVE_PROBE", "true")
    monkeypatch.setenv("FLEETPULSE_OPERATING_SYSTEM_REQUIRE_API_KEY", "true")
    monkeypatch.delenv("FLEETPULSE_OPERATING_SYSTEM_API_KEY", raising=False)
    monkeypatch.setenv(
        "K1L_OPERATING_COST_MONTHLY_JSON",
        """
        {
          "asOfDate": "2026-05-14",
          "months": [
            {
              "month": "2026-01",
              "miles": 314555.8,
              "driverPay": 346108.5,
              "fuel": 151524.27,
              "fleetMaintenance": 55734.77,
              "payroll": 89232.46,
              "otherOps": 101258.57
            }
          ]
        }
        """,
    )
    _patch_non_kpi_sources(
        monkeypatch,
        FleetOverview(
            total_vehicles=2,
            active=1,
            idle=1,
            scoped_device_count=2,
            raw_status_count=2,
            source_mode="live_filtered",
        ),
    )

    response = _client().get("/api/dashboard/validation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["projection_mode"] == "read_only"
    assert payload["summary"]["verified"] == 8
    assert payload["metric_summary"]["verified"] == 16
    assert payload["sections"]["k1l_final_cpm"]["status"] == "verified"
    assert payload["metrics"]["k1l_final_cpm"]["verified"] is True
    assert payload["sections"]["fleet_overview"]["status"] == "verified"
    assert payload["metrics"]["total_vehicles"]["status"] == "verified"
    assert payload["sections"]["data_connector"]["status"] == "verified"
    assert payload["sections"]["operating_system"]["status"] == "failed"
    assert payload["sections"]["alerts"]["status"] == "pending_no_data"
    assert payload["sections"]["agentic_monitor"]["status"] == "pending_no_audit"
    assert payload["summary"]["pending_no_data"] == 1
    assert payload["summary"]["pending_no_audit"] == 2
    assert any(row["blocked_by"] == "no_audit" for row in payload["pending_ledger"])


def test_dashboard_validation_does_not_verify_failed_or_missing_sources(monkeypatch):
    monkeypatch.delenv("K1L_OPERATING_COST_MONTHLY_JSON", raising=False)
    monkeypatch.delenv("GEOTAB_USERNAME", raising=False)
    monkeypatch.delenv("GEOTAB_PASSWORD", raising=False)
    monkeypatch.setenv("FLEETPULSE_OPERATING_SYSTEM_REQUIRE_API_KEY", "false")
    monkeypatch.setattr(
        validation_service,
        "get_fleet_overview",
        lambda: (_ for _ in ()).throw(RuntimeError("geotab disconnected")),
    )
    monkeypatch.setattr(validation_service, "get_vehicles", lambda: [])
    monkeypatch.setattr(validation_service, "get_location_stats", lambda: [])
    monkeypatch.setattr(validation_service, "get_safety_scores", lambda days=7: [])
    monkeypatch.setattr(validation_service, "get_recent_alerts", lambda hours=24: [])
    monkeypatch.setattr(validation_service, "record_probe", lambda *args, **kwargs: {})
    monkeypatch.setattr(validation_service, "last_seen_row_at", lambda probe_name: None)

    response = _client().get("/api/dashboard/validation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sections"]["k1l_final_cpm"]["status"] == "pending"
    assert payload["sections"]["fleet_overview"]["status"] == "failed"
    assert payload["metrics"]["total_vehicles"]["verified"] is False
    assert payload["sections"]["data_connector"]["status"] == "failed"
    assert payload["sections"]["operating_system"]["status"] == "verified"


def test_dashboard_validation_separates_geotab_json_rpc_from_odata_auth(monkeypatch):
    monkeypatch.setenv("GEOTAB_DATABASE", "k1logistics")
    monkeypatch.setenv("GEOTAB_USERNAME", "operator@example.com")
    monkeypatch.setenv("GEOTAB_PASSWORD", "secret")
    monkeypatch.setenv("FLEETPULSE_OPERATING_SYSTEM_REQUIRE_API_KEY", "false")
    monkeypatch.delenv("FLEETPULSE_DASHBOARD_VALIDATION_LIVE_PROBE", raising=False)
    monkeypatch.delenv("K1L_OPERATING_COST_MONTHLY_JSON", raising=False)

    response = _client().get("/api/dashboard/validation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sections"]["fleet_overview"]["status"] == "pending"
    assert payload["metrics"]["total_vehicles"]["status"] == "pending"
    assert payload["sections"]["data_connector"]["status"] == "pending"
