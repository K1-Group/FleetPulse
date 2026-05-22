"""Tests for FleetPulse configured operating hubs."""

from __future__ import annotations

import sys
import types
from pathlib import Path


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

from services import fleet_service  # noqa: E402
from services import monitor_service  # noqa: E402


def test_configured_hubs_include_requested_markets():
    expected = {
        "Austin Hub": "Austin, TX",
        "San Antonio Hub": "San Antonio, TX",
        "Atlanta Hub": "Atlanta, GA",
        "Little Rock Hub": "Little Rock, AR",
    }
    hubs_by_name = {location["name"]: location for location in fleet_service.LOCATIONS}

    for name, address in expected.items():
        assert hubs_by_name[name]["address"] == address
        assert isinstance(hubs_by_name[name]["lat"], float)
        assert isinstance(hubs_by_name[name]["lon"], float)


def test_monitor_centers_include_requested_hubs():
    expected_centers = {
        location["name"]: (location["lat"], location["lon"])
        for location in fleet_service.LOCATIONS
    }

    assert monitor_service.LOCATION_CENTERS == expected_centers
    for name in ("Austin Hub", "San Antonio Hub", "Atlanta Hub", "Little Rock Hub"):
        assert name in monitor_service.LOCATION_CENTERS


def test_location_stats_exposes_hubs_without_synthetic_vehicle_counts(monkeypatch):
    monkeypatch.setattr(fleet_service, "get_vehicles", lambda: [])

    stats_by_name = {location.name: location for location in fleet_service.get_location_stats()}

    for name in ("Austin Hub", "San Antonio Hub", "Atlanta Hub", "Little Rock Hub"):
        assert stats_by_name[name].vehicle_count == 0
        assert stats_by_name[name].active == 0
