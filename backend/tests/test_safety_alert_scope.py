"""Tests for safety and alert fleet scoping."""

from __future__ import annotations

from datetime import datetime, timezone
import sys
import types
from pathlib import Path

import pytest


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

from services import alert_service, safety_service  # noqa: E402


@pytest.fixture(autouse=True)
def clear_service_caches():
    safety_service._SAFETY_CACHE.clear()
    alert_service._ALERT_CACHE.clear()
    yield
    safety_service._SAFETY_CACHE.clear()
    alert_service._ALERT_CACHE.clear()


class ScopedGeotabClient:
    def get_devices(self):
        return [
            {
                "id": "truck-a",
                "name": "Truck A",
                "activeFrom": "2025-01-01T00:00:00Z",
                "activeTo": "2050-01-01T00:00:00Z",
                "groups": [{"id": "GroupVehicleId"}],
            },
            {
                "id": "truck-b",
                "name": "Truck B",
                "activeFrom": "2025-01-01T00:00:00Z",
                "activeTo": "2050-01-01T00:00:00Z",
                "groups": [{"id": "GroupVehicleId"}],
            },
            {
                "id": "trailer",
                "name": "Trailer",
                "activeFrom": "2025-01-01T00:00:00Z",
                "activeTo": "2050-01-01T00:00:00Z",
                "groups": [{"id": "GroupTrailerId"}],
            },
            {
                "id": "inactive",
                "name": "Inactive Truck",
                "activeFrom": "2024-01-01T00:00:00Z",
                "activeTo": "2024-06-01T00:00:00Z",
                "groups": [{"id": "GroupVehicleId"}],
            },
        ]

    def get_exception_events(self, *_args, **_kwargs):
        return [
            {
                "device": {"id": "truck-a"},
                "rule": {"name": "Posted Speeding"},
                "activeFrom": datetime(2026, 5, 10, 12, tzinfo=timezone.utc),
            },
            {
                "device": {"id": "trailer"},
                "rule": {"name": "Posted Speeding"},
                "activeFrom": datetime(2026, 5, 10, 12, tzinfo=timezone.utc),
            },
            {
                "device": {"id": "inactive"},
                "rule": {"name": "Posted Speeding"},
                "activeFrom": datetime(2026, 5, 10, 12, tzinfo=timezone.utc),
            },
            {
                "device": {"id": "truck-b"},
                "rule": {"name": ""},
                "activeFrom": datetime(2026, 5, 10, 12, tzinfo=timezone.utc),
            },
        ]


def test_safety_scores_use_operational_fleet_scope(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_SAFETY_DEMO_MODE", "false")
    monkeypatch.setattr(safety_service.GeotabClient, "get", lambda: ScopedGeotabClient())

    scores = safety_service.get_safety_scores(days=7)

    assert [score.vehicle_id for score in scores] == ["truck-a", "truck-b"]
    assert scores[0].event_count == 1
    assert scores[1].event_count == 0


def test_recent_alerts_use_operational_fleet_scope(monkeypatch):
    monkeypatch.setattr(alert_service.GeotabClient, "get", lambda: ScopedGeotabClient())

    alerts = alert_service.get_recent_alerts(hours=24)

    assert [alert.vehicle_id for alert in alerts] == ["truck-a"]
    assert alerts[0].vehicle_name == "Truck A"
    assert alerts[0].alert_type == "Posted Speeding"
