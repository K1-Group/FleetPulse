from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services.fleet_report_delivery_service import (  # noqa: E402
    EMAIL_WEBHOOK_ENV,
    SCHEDULE_PATH_ENV,
    calculate_next_run,
    get_due_report_schedule_status,
    get_report_schedule_status,
    record_report_schedule_attempt,
    save_report_schedule,
)


def test_weekly_monday_report_schedule_persists_recipients_and_next_run(monkeypatch, tmp_path):
    schedule_path = tmp_path / "fleet_report_schedule.json"
    monkeypatch.setenv(SCHEDULE_PATH_ENV, str(schedule_path))
    monkeypatch.delenv(EMAIL_WEBHOOK_ENV, raising=False)

    saved = save_report_schedule(
        {
            "enabled": True,
            "frequency": "weekly",
            "period": "weekly",
            "recipients": ["rami@k1group.net", "ops@k1logistics.com"],
            "send_time": "07:00",
            "timezone": "America/Chicago",
            "weekday": 0,
        }
    )

    assert saved["persistent_storage"] is True
    assert saved["schedule"]["recipients"] == ["rami@k1group.net", "ops@k1logistics.com"]
    assert saved["schedule"]["send_time"] == "07:00"
    assert saved["schedule"]["weekday"] == 0
    assert schedule_path.exists()

    first_status = get_report_schedule_status()
    second_status = get_report_schedule_status()

    assert first_status["schedule"]["updated_at"] == second_status["schedule"]["updated_at"]
    assert first_status["schedule"]["recipients"] == ["rami@k1group.net", "ops@k1logistics.com"]
    assert first_status["delivery_ready"] is False
    assert first_status["required_config"] == [EMAIL_WEBHOOK_ENV]

    next_run = calculate_next_run(
        first_status["schedule"],
        now=datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc),
    )
    assert next_run == "2026-05-25T07:00:00-05:00"


def test_due_weekly_schedule_is_idempotent_after_success(monkeypatch, tmp_path):
    monkeypatch.setenv(SCHEDULE_PATH_ENV, str(tmp_path / "fleet_report_schedule.json"))
    monkeypatch.setenv(EMAIL_WEBHOOK_ENV, "https://example.test/webhook")

    save_report_schedule(
        {
            "enabled": True,
            "frequency": "weekly",
            "period": "weekly",
            "recipients": ["rami@k1group.net"],
            "send_time": "07:00",
            "timezone": "America/Chicago",
            "weekday": 0,
        }
    )

    due = get_due_report_schedule_status("2026-05-25T12:00:00+00:00")

    assert due["due"] is True
    assert due["scheduled_for"] == "2026-05-25T07:00:00-05:00"
    assert due["run_key"] == "weekly:2026-05-25T07:00:00-05:00"

    record_report_schedule_attempt(
        message="Report delivery accepted.",
        run_key=due["run_key"],
        scheduled_for=due["scheduled_for"],
        status="sent",
    )
    after = get_due_report_schedule_status("2026-05-25T12:05:00+00:00")

    assert after["due"] is False
    assert after["reason"] == "already_sent"
    assert after["schedule"]["last_run_key"] == due["run_key"]
    assert after["schedule"]["recipients"] == ["rami@k1group.net"]
