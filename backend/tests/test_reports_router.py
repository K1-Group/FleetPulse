from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace


BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from _cache import clear_cached_prefix  # noqa: E402
from routers import reports  # noqa: E402


class FakeGeotabClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_devices(self):
        self.calls.append("devices")
        return [{"id": "truck-1", "name": "Truck 1"}]

    def get_trips(self, from_date=None, to_date=None):
        self.calls.append("trips")
        return [{"device": {"id": "truck-1"}, "distance": 16.0934}]

    def get_exception_events(self, from_date=None, to_date=None):
        self.calls.append("exceptions")
        return []


def test_report_generation_reuses_cached_source_backed_payload(monkeypatch):
    clear_cached_prefix("report:")
    fake_client = FakeGeotabClient()
    monkeypatch.setattr(reports.GeotabClient, "get", lambda: fake_client)
    monkeypatch.setattr(
        reports,
        "get_live_trailer_tracking",
        lambda: SimpleNamespace(
            summary=SimpleNamespace(total_trailers=1, custody_inferred=1),
            trailers=[],
        ),
    )

    first = reports._generate_report_payload("weekly")
    second = reports._generate_report_payload("weekly")

    assert first["source_status"] == "source_backed"
    assert first["period_start"]
    assert first["period_end"]
    assert "Window:" in first["html"]
    assert first["summary"]["total_vehicles"] == 1
    assert second["summary"]["total_distance_mi"] == first["summary"]["total_distance_mi"]
    assert fake_client.calls == ["devices", "trips", "exceptions"]


def test_report_generation_marks_trailer_tracking_partial_without_fake_rows(monkeypatch):
    clear_cached_prefix("report:")
    fake_client = FakeGeotabClient()
    monkeypatch.setattr(reports.GeotabClient, "get", lambda: fake_client)
    monkeypatch.setattr(
        reports,
        "get_live_trailer_tracking",
        lambda: (_ for _ in ()).throw(RuntimeError("OverLimitException API calls quota exceeded")),
    )

    payload = reports._generate_report_payload("weekly")

    assert payload["source_status"] == "partial_source_backed"
    assert payload["summary"]["trailers_tracked"] == 0
    assert payload["source_warnings"] == ["Trailer tracking unavailable: RuntimeError"]


def test_scheduled_report_does_not_generate_when_delivery_not_configured(monkeypatch):
    generated = False
    attempts: list[dict[str, str]] = []

    monkeypatch.setattr(
        reports,
        "get_due_report_schedule_status",
        lambda now=None: {
            "due": True,
            "delivery_ready": False,
            "schedule": {
                "enabled": True,
                "period": "weekly",
                "frequency": "weekly",
                "recipients": ["ops@example.com"],
            },
            "run_key": "weekly:2026-05-25T12:00:00+00:00",
            "scheduled_for": "2026-05-25T12:00:00+00:00",
        },
    )

    def fake_generate_report(period: str):
        nonlocal generated
        generated = True
        return {"period": period}

    monkeypatch.setattr(reports, "_generate_report_payload", fake_generate_report)

    def fake_record_attempt(**kwargs):
        attempts.append(kwargs)
        return {"schedule": {}, "next_run_at": None}

    monkeypatch.setattr(reports, "record_report_schedule_attempt", fake_record_attempt)

    result = asyncio.run(reports.run_scheduled_report())

    assert generated is False
    assert result["status"] == "needs_configuration"
    assert attempts == [
        {
            "message": "FLEETPULSE_REPORT_EMAIL_WEBHOOK_URL is required for scheduled report delivery.",
            "run_key": "weekly:2026-05-25T12:00:00+00:00",
            "scheduled_for": "2026-05-25T12:00:00+00:00",
            "status": "needs_configuration",
        }
    ]
