from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from _cache import clear_cached_prefix  # noqa: E402
from geotab_client import GeotabClient  # noqa: E402


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get(self, entity: str, **kwargs):
        self.calls.append((entity, kwargs))
        if entity == "Device":
            return [{"id": "truck-1"}]
        if entity == "Trip":
            return [{"device": {"id": "truck-1"}, "distance": 10}]
        return []


def _client(fake_api: FakeApi) -> GeotabClient:
    client = GeotabClient()
    client._api = fake_api
    client._auth_time = time.time()
    return client


def test_geotab_reads_are_cached_for_quota_window(monkeypatch):
    clear_cached_prefix("geotab:")
    monkeypatch.setenv("FLEETPULSE_GEOTAB_READ_CACHE_SECONDS", "75")
    fake_api = FakeApi()
    client = _client(fake_api)

    assert client.get_devices() == [{"id": "truck-1"}]
    assert client.get_devices() == [{"id": "truck-1"}]

    device_calls = [call for call in fake_api.calls if call[0] == "Device"]
    assert len(device_calls) == 1


def test_geotab_trip_cache_buckets_datetime_inputs_by_minute(monkeypatch):
    clear_cached_prefix("geotab:")
    monkeypatch.setenv("FLEETPULSE_GEOTAB_READ_CACHE_SECONDS", "75")
    fake_api = FakeApi()
    client = _client(fake_api)

    client.get_trips(
        datetime(2026, 5, 22, 12, 0, 10, tzinfo=timezone.utc),
        datetime(2026, 5, 22, 12, 5, 10, tzinfo=timezone.utc),
    )
    client.get_trips(
        datetime(2026, 5, 22, 12, 0, 40, tzinfo=timezone.utc),
        datetime(2026, 5, 22, 12, 5, 40, tzinfo=timezone.utc),
    )

    trip_calls = [call for call in fake_api.calls if call[0] == "Trip"]
    assert len(trip_calls) == 1
