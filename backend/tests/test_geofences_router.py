"""Tests for truthful Geotab geofence surfaces."""

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

from _cache import clear_cached_prefix  # noqa: E402
from routers import geofences  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(geofences.router, prefix="/api/geofences")
    return TestClient(app)


def test_geofence_reads_return_empty_when_geotab_unavailable(monkeypatch):
    clear_cached_prefix("geofences:")

    def raise_geotab():
        raise RuntimeError("geotab down")

    monkeypatch.setattr(geofences.GeotabClient, "get", staticmethod(raise_geotab))

    client = _client()

    zones = client.get("/api/geofences/zones")
    activity = client.get("/api/geofences/activity")

    assert zones.status_code == 200
    assert activity.status_code == 200
    assert zones.json() == []
    assert activity.json() == []
    assert "demo-zone" not in zones.text
    assert "Budget-LV-042" not in activity.text


def test_geofence_create_does_not_simulate_success_when_geotab_fails(monkeypatch):
    clear_cached_prefix("geofences:")

    class BrokenGeotabClient:
        def add_zone(self, zone_data):
            raise RuntimeError("write unavailable")

    monkeypatch.setattr(
        geofences.GeotabClient,
        "get",
        staticmethod(lambda: BrokenGeotabClient()),
    )

    response = _client().post(
        "/api/geofences/create",
        json={
            "name": "Real customer yard",
            "latitude": 32.75,
            "longitude": -97.33,
            "radius_meters": 200,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"].startswith("Geotab geofence creation is unavailable")
    assert "demo" not in response.text.lower()
