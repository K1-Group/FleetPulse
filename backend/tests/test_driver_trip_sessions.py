"""Tests for K1 driver-session trip metrics."""
from __future__ import annotations

from datetime import datetime, timezone
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
