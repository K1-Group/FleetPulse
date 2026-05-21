"""Tests for Geotab-backed maintenance decision intelligence."""

from __future__ import annotations

import asyncio
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

from _cache import clear_cached_prefix  # noqa: E402
from routers import maintenance  # noqa: E402


def test_maintenance_intelligence_prioritizes_repeated_cooling_fault(monkeypatch):
    clear_cached_prefix("maintenance_intelligence:")

    async def _fault_trends(days: int):
        return {
            "period_days": days,
            "feed_status": "ok",
            "faults": [
                *[
                    {
                        "vehicle_id": "b11F",
                        "vehicle_name": "2560",
                        "FaultCode": "1659",
                        "FaultCodeDescription": "Engine coolant system thermostat 1",
                        "FailureModeDescription": "Data valid but below normal operational range - moderately severe level",
                        "IsPersistentCycle": True,
                        "date": "2026-05-21",
                    }
                    for _ in range(6)
                ],
                {
                    "vehicle_id": "b11F",
                    "vehicle_name": "2560",
                    "FaultCode": "639",
                    "FaultCodeDescription": "J1939 network #1 primary vehicle network",
                    "FailureModeDescription": "Data erratic intermittent or incorrect",
                    "IsPersistentCycle": True,
                    "date": "2026-05-21",
                },
            ],
        }

    monkeypatch.setattr(maintenance, "_fault_trends_from_data_connector", _fault_trends)
    monkeypatch.setattr(maintenance, "_get_devices_cached", lambda: [])
    monkeypatch.setattr(maintenance, "_get_fleet_faults", lambda days=30: {})

    payload = asyncio.run(maintenance.get_maintenance_intelligence(days=30))

    assert payload["source_mode"] == "geotab_data_connector_fault_trends"
    assert payload["automation_mode"] == "ai_recommends_human_executes"
    assert payload["summary"]["vehicles_with_faults"] == 1
    assert payload["decisions"][0]["vehicle_name"] == "2560"
    assert payload["decisions"][0]["risk_score"] >= 85
    assert payload["decisions"][0]["predicted_issue"] == "Cooling system failure risk"
    assert "Recurring code pattern: 1659" in payload["decisions"][0]["evidence"]
