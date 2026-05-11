"""Tests for safety scoring timeout behavior."""

from __future__ import annotations

import sys
import types
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

from services import safety_service  # noqa: E402


class TimeoutGeotabClient:
    def get_devices(self):
        raise TimeoutError("Geotab API call timed out after 10.0s")


def test_safety_scores_timeout_returns_empty_live_result(monkeypatch):
    safety_service._SAFETY_CACHE.clear()
    monkeypatch.setenv("FLEETPULSE_SAFETY_DEMO_MODE", "false")
    monkeypatch.setattr(safety_service.GeotabClient, "get", lambda: TimeoutGeotabClient())

    assert safety_service.get_safety_scores(days=7) == []
