from __future__ import annotations

from datetime import datetime, timezone

from configs.employee_workforce import EmployeeWorkforceConfig
from services.employee_workforce_service import build_employee_workforce_dataset


def _now() -> datetime:
    return datetime(2026, 5, 30, 18, tzinfo=timezone.utc)


def test_employee_workforce_pending_config_does_not_fabricate_rows():
    dataset = build_employee_workforce_dataset(
        [],
        config=EmployeeWorkforceConfig(),
        now=_now(),
    )

    assert dataset["projection_mode"] == "read_only"
    assert dataset["source_authority"] == "Time Doctor employee time and activity export"
    assert dataset["summary"]["employees"] == 0
    assert dataset["employees"] == []
    assert dataset["validation"]["status"] == "pending"
    assert "FLEETPULSE_TIMEDOCTOR_ACTIVITY_FEED_PATH" in dataset["validation"]["required_config"][1]


def test_employee_workforce_summarizes_time_doctor_activity_rows():
    config = EmployeeWorkforceConfig(lookback_days=7, timezone="America/Chicago")
    rows = [
        {
            "employee_id": "E1",
            "employee_name": "Ops One",
            "department": "Dispatch",
            "date": "2026-05-30",
            "worked_minutes": "480",
            "productive_minutes": "420",
            "idle_minutes": "30",
            "project": "Dispatch Board",
        },
        {
            "employee_id": "E2",
            "employee_name": "Ops Two",
            "department": "Billing",
            "date": "2026-05-29",
            "worked_minutes": "360",
            "productive_minutes": "300",
            "idle_minutes": "45",
            "project": "Invoice Audit",
        },
    ]

    dataset = build_employee_workforce_dataset(
        rows,
        config=config,
        now=_now(),
        source_status={"status": "healthy", "message": "Loaded test feed.", "required_config": [], "row_count": 2},
    )

    assert dataset["validation"]["status"] == "verified"
    assert dataset["summary"]["employees"] == 2
    assert dataset["summary"]["active_today"] == 1
    assert dataset["summary"]["worked_hours"] == 14.0
    assert dataset["summary"]["missing_timesheet_count"] == 1
    assert dataset["employees"][0]["employee_name"] == "Ops One"
    assert dataset["employees"][0]["productivity_pct"] == 87.5
