"""Tests for live trailer tracking projection."""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from pathlib import Path

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

from models import ControlTowerTrailerEvent  # noqa: E402
from services import trailer_tracking_service  # noqa: E402


class FakeGeotabClient:
    def get_devices(self):
        return [
            {
                "id": "trailer-1",
                "name": "H03473",
                "groups": [{"id": "GroupTrailerId"}],
            },
            {
                "id": "tractor-219",
                "name": "Tractor 219",
                "groups": [{"id": "GroupVehicleId"}],
            },
        ]

    def get_device_status_info(self):
        return [
            {
                "device": {"id": "trailer-1"},
                "dateTime": "2026-05-12T17:20:00Z",
                "latitude": 32.90001,
                "longitude": -97.28001,
                "speed": 0,
                "bearing": 180,
            },
            {
                "device": {"id": "tractor-219"},
                "dateTime": "2026-05-12T17:20:00Z",
                "latitude": 32.90000,
                "longitude": -97.28000,
                "speed": 0,
                "bearing": 180,
            },
        ]

    def get_trips(self, from_date=None, to_date=None):
        return [
            {
                "device": {"id": "tractor-219"},
                "driver": {"id": "driver-1", "name": "K1 Driver"},
                "stopDateTime": "2026-05-12T17:19:00Z",
            }
        ]


def test_live_trailer_tracking_merges_geotab_xtra_and_driver(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_TRAILER_MATCH_RADIUS_METERS", "150")
    monkeypatch.setattr(
        trailer_tracking_service,
        "GeotabClient",
        type("FakeGeotabClientFactory", (), {"get": staticmethod(lambda: FakeGeotabClient())}),
    )
    monkeypatch.setattr(
        trailer_tracking_service,
        "_now",
        lambda: datetime(2026, 5, 12, 17, 30, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        trailer_tracking_service,
        "get_xtra_lease_projection",
        lambda config: types.SimpleNamespace(
            events=[
                ControlTowerTrailerEvent(
                    id="xtra-1",
                    trailer_id="H03473",
                    event_type="geofence_exit",
                    location="Haslet, TX",
                    timestamp=datetime(2026, 5, 12, 17, 18, 51, tzinfo=timezone.utc),
                    source_authority="Outlook / XTRA Lease",
                )
            ],
            last_email_received="2026-05-12T17:18:51+00:00",
        ),
    )

    response = trailer_tracking_service.get_live_trailer_tracking()

    assert response.summary.total_trailers == 1
    assert response.summary.gps_active == 1
    assert response.summary.xtra_event_trailers == 1
    assert response.summary.custody_inferred == 1
    trailer = response.trailers[0]
    assert trailer.trailer_id == "H03473"
    assert trailer.xtra_last_event is not None
    assert trailer.custody.vehicle_name == "Tractor 219"
    assert trailer.custody.driver_name == "K1 Driver"
    assert trailer.custody.confidence == "high"
