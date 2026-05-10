"""Tests for FleetPulse live fleet scoping."""

from __future__ import annotations

import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services import fleet_service  # noqa: E402


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
