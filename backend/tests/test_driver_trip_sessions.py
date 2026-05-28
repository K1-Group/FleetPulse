"""Tests for K1 driver-session trip metrics."""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import types
import unittest

# Make backend/ importable regardless of how pytest is invoked.
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Stub mygeotab so geotab_client imports without the SDK installed.
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

if "dotenv" not in sys.modules:
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **kw: None
    sys.modules["dotenv"] = dotenv

from services.fleet_service import summarize_driver_trip_sessions  # noqa: E402


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 9, hour, minute, tzinfo=timezone.utc)


class DriverTripSessionTests(unittest.TestCase):
    def test_default_stop_threshold_counts_only_stops_over_sixty_minutes(self):
        trips = [
            {
                "driver": {"id": "driver-default", "name": "Driver Default"},
                "device": {"id": "truck-default", "name": "Truck Default"},
                "start": _dt(6),
                "stop": _dt(7),
                "distance": 40,
            },
            {
                "driver": {"id": "driver-default", "name": "Driver Default"},
                "device": {"id": "truck-default", "name": "Truck Default"},
                "start": _dt(7, 45),
                "stop": _dt(8),
                "distance": 10,
            },
            {
                "driver": {"id": "driver-default", "name": "Driver Default"},
                "device": {"id": "truck-default", "name": "Truck Default"},
                "start": _dt(9, 15),
                "stop": _dt(10),
                "distance": 30,
            },
        ]

        original = os.environ.pop("FLEETPULSE_STOP_THRESHOLD_MINUTES", None)
        try:
            metrics = summarize_driver_trip_sessions(
                trips,
                now=_dt(11),
                driver_logout_gap_minutes=600,
                target_trip_hours=12,
            )
        finally:
            if original is not None:
                os.environ["FLEETPULSE_STOP_THRESHOLD_MINUTES"] = original

        self.assertEqual(metrics["trip_count"], 1)
        self.assertEqual(metrics["total_stops"], 1)

    def test_driver_round_trip_with_stops_counts_as_one_trip(self):
        trips = [
            {
                "driver": {"id": "driver-1", "name": "Driver One"},
                "device": {"id": "truck-1", "name": "Truck 1"},
                "start": _dt(6),
                "stop": _dt(8),
                "distance": 100,
            },
            {
                "driver": {"id": "driver-1", "name": "Driver One"},
                "device": {"id": "truck-1", "name": "Truck 1"},
                "start": _dt(8, 4),
                "stop": _dt(10),
                "distance": 90,
            },
            {
                "driver": {"id": "driver-1", "name": "Driver One"},
                "device": {"id": "truck-1", "name": "Truck 1"},
                "start": _dt(10, 20),
                "stop": _dt(18, 30),
                "distance": 210,
            },
        ]

        metrics = summarize_driver_trip_sessions(
            trips,
            now=_dt(19),
            stop_threshold_minutes=5,
            driver_logout_gap_minutes=600,
            target_trip_hours=12,
        )

        self.assertEqual(metrics["trip_count"], 1)
        self.assertEqual(metrics["total_stops"], 1)
        self.assertEqual(metrics["avg_duration_hours"], 12.5)
        self.assertEqual(metrics["trips_meeting_target"], 1)
        self.assertEqual(metrics["trips_under_target"], 0)

    def test_long_stop_details_include_driver_and_geofence_when_available(self):
        trips = [
            {
                "driver": {"id": "driver-yard", "name": "Driver Yard"},
                "device": {"id": "truck-yard", "name": "Truck Yard"},
                "start": _dt(6),
                "stop": _dt(7),
                "stopPoint": {"x": -97.2197, "y": 32.8012},
                "distance": 40,
            },
            {
                "driver": {"id": "driver-yard", "name": "Driver Yard"},
                "device": {"id": "truck-yard", "name": "Truck Yard"},
                "start": _dt(8, 15),
                "stop": _dt(9),
                "distance": 30,
            },
        ]

        metrics = summarize_driver_trip_sessions(
            trips,
            now=_dt(10),
            stop_threshold_minutes=60,
            driver_logout_gap_minutes=600,
            target_trip_hours=12,
        )

        self.assertEqual(metrics["total_stops"], 1)
        self.assertEqual(len(metrics["long_stops"]), 1)
        stop = metrics["long_stops"][0]
        self.assertEqual(stop["driver_name"], "Driver Yard")
        self.assertEqual(stop["device_name"], "Truck Yard")
        self.assertEqual(stop["duration_minutes"], 75)
        self.assertEqual(stop["geofence"], "Fort Worth Yard")
        self.assertEqual(stop["address"], "4200 Gravel Dr, Fort Worth, TX 76118")
        self.assertEqual(stop["location_source"], "configured_fleet_hub_geofence")

    def test_long_logout_gap_starts_a_new_driver_trip(self):
        trips = [
            {
                "driver": {"id": "driver-2"},
                "device": {"id": "truck-2"},
                "startDateTime": "2026-05-09T01:00:00Z",
                "stopDateTime": "2026-05-09T03:00:00Z",
                "distance": 25,
            },
            {
                "driver": {"id": "driver-2"},
                "device": {"id": "truck-2"},
                "startDateTime": "2026-05-09T14:30:00Z",
                "stopDateTime": "2026-05-09T16:30:00Z",
                "distance": 25,
            },
        ]

        metrics = summarize_driver_trip_sessions(
            trips,
            now=_dt(17),
            stop_threshold_minutes=5,
            driver_logout_gap_minutes=600,
            target_trip_hours=12,
        )

        self.assertEqual(metrics["trip_count"], 2)
        self.assertEqual(metrics["total_stops"], 0)
        self.assertEqual(metrics["trips_under_target"], 2)
