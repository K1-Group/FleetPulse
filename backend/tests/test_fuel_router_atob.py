"""Tests for Fuel Analytics AtoB import router."""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
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

from _cache import clear_cached_prefix  # noqa: E402
from routers import fuel  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(fuel.router, prefix="/api/fuel")
    return TestClient(app)


def _sample_csv(transaction_id: str = "A-100") -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    return (
        "Transaction ID,Transaction Date,Merchant,Amount,Gallons,Vehicle\n"
        f"{transaction_id},{today},Pilot,250.00,50.0,5439 Idealease -HDS DFW\n"
    )


def test_atob_import_endpoint_summarizes_actual_expenses(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEETPULSE_ATOB_FUEL_STATE_PATH", str(tmp_path / "atob-state.json"))
    clear_cached_prefix("fuel:")

    response = _client().post(
        "/api/fuel/atob/import",
        json={
            "filename": "atob.csv",
            "content": _sample_csv(),
            "dry_run": False,
        },
    )
    summary = _client().get("/api/fuel/atob/summary?days=30")

    assert response.status_code == 200
    assert response.json()["imported_count"] == 1
    assert summary.status_code == 200
    assert summary.json()["transaction_count"] == 1
    assert summary.json()["total_cost"] == 250.0


def test_fuel_summary_prefers_atob_actual_cost_when_imported(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEETPULSE_ATOB_FUEL_STATE_PATH", str(tmp_path / "atob-state.json"))
    clear_cached_prefix("fuel:")

    class FakeGeotabClient:
        def get_trips(self, from_date=None, to_date=None):
            return [
                {
                    "start": datetime.now(timezone.utc).isoformat(),
                    "distance": 160.934,
                    "device": {"id": "device-1"},
                }
            ]

        def get_exception_events(self, from_date=None, to_date=None):
            return []

        def get_devices(self):
            return [{"id": "device-1", "name": "5439 Idealease -HDS DFW"}]

    monkeypatch.setattr(fuel.GeotabClient, "get", staticmethod(lambda: FakeGeotabClient()))

    client = _client()
    client.post(
        "/api/fuel/atob/import",
        json={
            "filename": "atob.csv",
            "content": _sample_csv("A-200"),
            "dry_run": False,
        },
    )
    response = client.get("/api/fuel/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["fuel_cost_source"] == "atob_manual_import"
    assert payload["period_30d"]["total_cost"] == 250.0
    assert payload["period_30d"]["actual_fuel_cost"] is True


def test_atob_sharepoint_sync_endpoint_requires_key(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_ATOB_SHAREPOINT_INGESTION_API_KEY", "expected")

    response = _client().post("/api/fuel/atob/sharepoint/sync", json={"dry_run": True})

    assert response.status_code == 401


def test_atob_sharepoint_sync_endpoint_runs_with_valid_key(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_ATOB_SHAREPOINT_INGESTION_API_KEY", "expected")

    class FakeResult:
        dry_run = False
        imported_count = 1

        def as_dict(self):
            return {
                "status": "ok",
                "source_authority": "SharePoint / AtoB fuel folder",
                "imported_count": 1,
            }

    monkeypatch.setattr(fuel, "sync_atob_sharepoint_folder", lambda config, dry_run=False: FakeResult())

    response = _client().post(
        "/api/fuel/atob/sharepoint/sync",
        json={"dry_run": False},
        headers={"X-FleetPulse-AtoB-Key": "expected"},
    )

    assert response.status_code == 200
    assert response.json()["imported_count"] == 1


def test_atob_sharepoint_status_does_not_expose_secret(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_ATOB_SHAREPOINT_ENABLED", "true")
    monkeypatch.setenv("FLEETPULSE_ATOB_SHAREPOINT_INGESTION_API_KEY", "expected")

    response = _client().get("/api/fuel/atob/sharepoint/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_key_required"] is True
    assert "expected" not in response.text


def test_operating_cost_endpoint_returns_weekly_snapshot(monkeypatch):
    async def fake_snapshot(days=90, start=None, end=None):
        return {
            "period_start": start,
            "period_end": end or "2026-05-14",
            "projection_mode": "read_only",
            "complete_cost_available": False,
            "summary": {"known_cost_per_mile": 0.62},
            "weekly": [],
        }

    monkeypatch.setattr(fuel, "get_operating_cost_snapshot", fake_snapshot)

    response = _client().get("/api/fuel/operating-cost?start=2026-01-01&end=2026-05-14")

    assert response.status_code == 200
    assert response.json()["summary"]["known_cost_per_mile"] == 0.62
