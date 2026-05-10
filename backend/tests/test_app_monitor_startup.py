"""Tests for FleetPulse startup behavior."""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def test_startup_does_not_start_monitor_by_default(monkeypatch):
    called = {"start": False}
    fake_monitor = types.ModuleType("services.monitor_service")

    def start_monitor():
        called["start"] = True

    fake_monitor.start_monitor = start_monitor
    monkeypatch.setitem(sys.modules, "services.monitor_service", fake_monitor)
    monkeypatch.delenv("FLEETPULSE_MONITOR_ENABLED", raising=False)

    from app import startup_event

    asyncio.run(startup_event())

    assert called["start"] is False
