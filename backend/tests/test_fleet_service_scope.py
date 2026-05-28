"""Tests for FleetPulse live fleet scoping."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services import fleet_service  # noqa: E402


@pytest.fixture(autouse=True)
def clear_fleet_service_cache():
    fleet_service._CACHE.clear()
    yield
    fleet_service._CACHE.clear()


class FakeGeotabClient:
    def get_devices(self):
        return [
            {
                "id": "truck-active",
                "name": "Truck Active",
                "activeFrom": "2025-01-01T00:00:00Z",
                "activeTo": "2050-01-01T00:00:00Z",
                "groups": [{"id": "GroupVehicleId"}],
            },
            {
                "id": "truck-stale",
                "name": "Truck Stale",
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
                "id": "inactive-truck",
                "name": "Inactive Truck",
                "activeFrom": "2024-01-01T00:00:00Z",
                "activeTo": "2024-06-01T00:00:00Z",
                "groups": [{"id": "GroupVehicleId"}],
            },
        ]

    def get_device_status_info(self):
        return [
            {
                "device": {"id": "truck-active"},
                "dateTime": "2050-01-01T00:00:00Z",
                "isDriving": True,
                "speed": 45,
                "latitude": 32.8,
                "longitude": -97.2,
            },
            {
                "device": {"id": "truck-stale"},
                "dateTime": "2024-01-01T00:00:00Z",
                "isDriving": False,
                "speed": 0,
                "latitude": 32.8,
                "longitude": -97.2,
            },
        ]

    def get_trips(self, *_args, **_kwargs):
        return [
            {
                "device": {"id": "truck-active"},
                "driver": {"id": "driver-1"},
                "startDateTime": "2026-05-10T18:00:00Z",
                "stopDateTime": "2026-05-10T19:00:00Z",
                "distance": 100,
            },
            {
                "device": {"id": "trailer"},
                "driver": {"id": "driver-2"},
                "startDateTime": "2026-05-10T18:00:00Z",
                "stopDateTime": "2026-05-10T19:00:00Z",
                "distance": 100,
            },
        ]


def test_fleet_overview_filters_trailers_inactive_and_stale_status(monkeypatch):
    monkeypatch.setattr(fleet_service.GeotabClient, "get", lambda: FakeGeotabClient())
    monkeypatch.setenv("FLEETPULSE_STATUS_STALE_HOURS", "24")

    overview = fleet_service.get_fleet_overview()

    assert overview.total_vehicles == 2
    assert overview.raw_device_count == 4
    assert overview.scoped_device_count == 2
    assert overview.active == 1
    assert overview.offline == 1
    assert overview.stale_status_count == 1
    assert overview.total_trips_today == 1


def test_vehicle_list_hides_stale_positions(monkeypatch):
    monkeypatch.setattr(fleet_service.GeotabClient, "get", lambda: FakeGeotabClient())
    monkeypatch.setenv("FLEETPULSE_STATUS_STALE_HOURS", "24")

    vehicles = fleet_service.get_vehicles()

    assert [vehicle.id for vehicle in vehicles] == ["truck-active", "truck-stale"]
    assert vehicles[0].status == fleet_service.VehicleStatus.ACTIVE
    assert vehicles[0].position is not None
    assert vehicles[1].status == fleet_service.VehicleStatus.OFFLINE
    assert vehicles[1].position is None


def test_fleet_overview_uses_cached_live_data_after_timeout(monkeypatch):
    monkeypatch.setattr(fleet_service.GeotabClient, "get", lambda: FakeGeotabClient())
    monkeypatch.setenv("FLEETPULSE_CACHE_TTL_SECONDS", "0")
    monkeypatch.setenv("FLEETPULSE_CACHE_FALLBACK_SECONDS", "300")

    first = fleet_service.get_fleet_overview()

    class TimeoutGeotabClient(FakeGeotabClient):
        def get_devices(self):
            raise TimeoutError("geotab unavailable")

    monkeypatch.setattr(fleet_service.GeotabClient, "get", lambda: TimeoutGeotabClient())
    second = fleet_service.get_fleet_overview()

    assert first.total_vehicles == 2
    assert second.total_vehicles == 2
    assert second.source_mode == "cached_after_geotab_timeout"


def test_fleet_overview_exposes_long_stop_location_details(monkeypatch):
    class LongStopGeotabClient(FakeGeotabClient):
        def get_trips(self, *_args, **_kwargs):
            return [
                {
                    "device": {"id": "truck-active", "name": "Truck Active"},
                    "driver": {"id": "driver-1", "name": "Driver One"},
                    "startDateTime": "2026-05-10T18:00:00Z",
                    "stopDateTime": "2026-05-10T19:00:00Z",
                    "stopPoint": {"x": -97.2197, "y": 32.8012},
                    "distance": 50,
                },
                {
                    "device": {"id": "truck-active", "name": "Truck Active"},
                    "driver": {"id": "driver-1", "name": "Driver One"},
                    "startDateTime": "2026-05-10T20:30:00Z",
                    "stopDateTime": "2026-05-10T21:30:00Z",
                    "distance": 50,
                },
            ]

    monkeypatch.setattr(fleet_service.GeotabClient, "get", lambda: LongStopGeotabClient())
    monkeypatch.setenv("FLEETPULSE_STOP_THRESHOLD_MINUTES", "60")

    overview = fleet_service.get_fleet_overview()

    assert overview.total_stops_today == 1
    assert overview.stop_threshold_minutes == 60
    assert len(overview.long_stops_today) == 1
    stop = overview.long_stops_today[0]
    assert stop.driver_name == "Driver One"
    assert stop.device_name == "Truck Active"
    assert stop.duration_minutes == 90
    assert stop.geofence == "Fort Worth Yard"
    assert stop.address == "4200 Gravel Dr, Fort Worth, TX 76118"
    assert stop.source_authority == "Geotab"
    assert stop.projection_mode == "read_only"


def test_fleet_overview_includes_current_not_moving_after_last_trip(monkeypatch):
    class CurrentStoppedGeotabClient(FakeGeotabClient):
        def get_device_status_info(self):
            now = datetime.now(timezone.utc)
            return [
                {
                    "device": {"id": "truck-active"},
                    "dateTime": now.isoformat(),
                    "isDriving": False,
                    "speed": 0,
                    "latitude": 32.8012,
                    "longitude": -97.2197,
                }
            ]

        def get_trips(self, *_args, **_kwargs):
            now = datetime.now(timezone.utc)
            return [
                {
                    "device": {"id": "truck-active", "name": "Truck Active"},
                    "driver": {"id": "driver-1", "name": "Driver One"},
                    "startDateTime": (now - timedelta(minutes=150)).isoformat(),
                    "stopDateTime": (now - timedelta(minutes=90)).isoformat(),
                    "stopPoint": {"x": -97.2197, "y": 32.8012},
                    "distance": 50,
                }
            ]

    monkeypatch.setattr(fleet_service.GeotabClient, "get", lambda: CurrentStoppedGeotabClient())
    monkeypatch.setenv("FLEETPULSE_STOP_THRESHOLD_MINUTES", "60")

    overview = fleet_service.get_fleet_overview()

    assert overview.total_stops_today == 1
    assert len(overview.long_stops_today) == 1
    stop = overview.long_stops_today[0]
    assert stop.driver_name == "Driver One"
    assert stop.device_name == "Truck Active"
    assert stop.duration_minutes >= 89
    assert stop.resumed_at is None
    assert stop.geofence == "Fort Worth Yard"
    assert stop.address == "4200 Gravel Dr, Fort Worth, TX 76118"
    assert stop.source_authority == "Geotab"
    assert stop.projection_mode == "read_only"


def test_vehicle_list_returns_empty_without_cache_after_timeout(monkeypatch):
    class TimeoutGeotabClient:
        def get_devices(self):
            raise TimeoutError("geotab unavailable")

    monkeypatch.setattr(fleet_service.GeotabClient, "get", lambda: TimeoutGeotabClient())
    monkeypatch.setenv("FLEETPULSE_CACHE_TTL_SECONDS", "0")

    assert fleet_service.get_vehicles() == []
