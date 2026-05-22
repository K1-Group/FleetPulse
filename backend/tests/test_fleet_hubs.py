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
from models import Vehicle, VehiclePosition, VehicleStatus  # noqa: E402
from services import monitor_service  # noqa: E402
from services.hub_config_service import MILES_TO_METERS, normalize_hub_config  # noqa: E402


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
        assert hubs_by_name[name]["radius_miles"] == 25.0
        assert hubs_by_name[name]["radius_meters"] == 25.0 * MILES_TO_METERS
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


def test_location_stats_counts_assets_inside_configured_hub_radius(monkeypatch):
    monkeypatch.setattr(
        fleet_service,
        "get_vehicles",
        lambda: [
            Vehicle(
                id="austin-1",
                name="4596 new truck sleeper",
                status=VehicleStatus.ACTIVE,
                position=VehiclePosition(latitude=30.3396606, longitude=-97.6626816),
                location_name=fleet_service._nearest_location(30.3396606, -97.6626816),
            ),
            Vehicle(
                id="san-antonio-1",
                name="0386 New Truck Sleeper",
                status=VehicleStatus.PARKED,
                position=VehiclePosition(latitude=29.5025787, longitude=-98.3705826),
                location_name=fleet_service._nearest_location(29.5025787, -98.3705826),
            ),
            Vehicle(
                id="atlanta-1",
                name="2687 idlelease Atlanta",
                status=VehicleStatus.ACTIVE,
                position=VehiclePosition(latitude=33.5443344, longitude=-84.5634079),
                location_name=fleet_service._nearest_location(33.5443344, -84.5634079),
            ),
            Vehicle(
                id="little-rock-1",
                name="3052371",
                status=VehicleStatus.PARKED,
                position=VehiclePosition(latitude=34.7354355, longitude=-92.2519302),
                location_name=fleet_service._nearest_location(34.7354355, -92.2519302),
            ),
        ],
    )

    stats_by_name = {location.name: location for location in fleet_service.get_location_stats()}

    assert stats_by_name["Austin Hub"].vehicle_count == 1
    assert stats_by_name["Austin Hub"].active == 1
    assert stats_by_name["San Antonio Hub"].vehicle_count == 1
    assert stats_by_name["San Antonio Hub"].active == 0
    assert stats_by_name["Atlanta Hub"].vehicle_count == 1
    assert stats_by_name["Atlanta Hub"].active == 1
    assert stats_by_name["Little Rock Hub"].vehicle_count == 1
    assert stats_by_name["Little Rock Hub"].active == 0


def test_hub_config_normalizes_json_payload():
    hubs = normalize_hub_config(
        {
            "default_radius_miles": 7,
            "hubs": [
                {
                    "name": "Test Hub",
                    "address": "Test, TX",
                    "latitude": "30.1",
                    "longitude": "-97.2",
                }
            ],
        }
    )

    assert hubs == [
        {
            "name": "Test Hub",
            "address": "Test, TX",
            "lat": 30.1,
            "lon": -97.2,
            "radius_miles": 7.0,
            "radius_meters": 7.0 * MILES_TO_METERS,
        }
    ]
