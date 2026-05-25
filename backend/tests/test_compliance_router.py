"""Tests for source-backed compliance endpoints."""

from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta, timezone
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
from routers import compliance  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(compliance.router, prefix="/api/compliance")
    return TestClient(app)


def test_hos_summary_returns_unavailable_without_demo_fallback(monkeypatch):
    clear_cached_prefix("compliance:")

    def raise_geotab():
        raise RuntimeError("geotab down")

    monkeypatch.setattr(compliance.GeotabClient, "get", staticmethod(raise_geotab))

    response = _client().get("/api/compliance/hos-summary")

    assert response.status_code == 200
    payload = response.json()
    assert "demo" not in payload
    assert payload["summary"]["total_drivers"] == 0
    assert payload["drivers"] == []
    assert payload["violations"] == []
    assert payload["source_status"]["status"] == "unavailable"
    assert "Budget-LV-042" not in response.text


def test_inspection_readiness_marks_unconfigured_feeds_as_awaiting(monkeypatch):
    clear_cached_prefix("compliance:")
    now = datetime.now(timezone.utc)

    class FakeGeotabClient:
        def get_devices(self):
            return [{"id": "device-1", "name": "Truck 1"}]

        def get_device_status_info(self):
            return [{"device": {"id": "device-1"}}]

        def get_trips(self, from_date=None, to_date=None):
            return [
                {
                    "device": {"id": "device-1"},
                    "start": now.isoformat(),
                    "stop": (now + timedelta(hours=1)).isoformat(),
                }
            ]

    monkeypatch.setattr(
        compliance.GeotabClient,
        "get",
        staticmethod(lambda: FakeGeotabClient()),
    )

    response = _client().get("/api/compliance/inspection-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert "demo" not in payload
    assert payload["total_vehicles"] == 1
    assert payload["vehicles_inspected_today"] is None
    assert payload["last_audit_date"] is None
    assert payload["next_audit_date"] is None
    assert payload["source_status"]["status"] == "partial"

    checklist = {item["item"]: item for item in payload["checklist"]}
    assert checklist["ELD Device Connected"]["status"] == "pass"
    assert checklist["GPS Signal Active"]["status"] == "pass"
    assert checklist["HOS Records (7-day)"]["status"] == "pass"
    assert checklist["Vehicle Registration"]["status"] == "awaiting_feed"
    assert checklist["Insurance Documentation"]["status"] == "awaiting_feed"
