"""Tests for HR recruiting worklist calculations."""

from __future__ import annotations

import json
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services.hr_recruiting_service import (  # noqa: E402
    HrRecruitingConfig,
    build_hr_recruiting_dataset,
    get_hr_recruiting_dataset,
    import_hr_recruiting_snapshot,
)


def _config() -> HrRecruitingConfig:
    return HrRecruitingConfig(
        table_id="01KR00WV4YHCB6BMYDE1EG7HEM",
        source="zapier_table",
        sla_hours=(24, 48, 72),
    )


def test_hr_recruiting_dataset_calculates_age_stale_and_process_time() -> None:
    now = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    rows = [
        {
            "source_email_id": "outlook-message-1",
            "applicant": "Private Applicant One",
            "worklist": "Recruiter Review",
            "status": "Assigned",
            "first_assigned_at": "2026-05-14T10:00:00Z",
            "current_worklist_entered_at": "2026-05-15T00:00:00Z",
            "phone": "555-0100",
            "email": "private.one@example.com",
            "ssn": "123-45-6789",
        },
        {
            "source_email_id": "outlook-message-1",
            "applicant": "Private Applicant One",
            "worklist": "Recruiter Review",
            "status": "Assigned",
            "first_assigned_at": "2026-05-14T10:00:00Z",
            "current_worklist_entered_at": "2026-05-15T00:00:00Z",
        },
        {
            "applicant": "Private Applicant Two",
            "worklist": "Safety Review",
            "status": "In Progress",
            "first_assigned_at": "2026-05-12T10:00:00Z",
            "current_worklist_entered_at": "2026-05-12T12:00:00Z",
        },
        {
            "source_email_id": "outlook-message-3",
            "applicant": "Private Applicant Three",
            "worklist": "Background Check",
            "status": "Completed",
            "first_assigned_at": "2026-05-15T08:00:00Z",
            "current_worklist_entered_at": "2026-05-15T08:00:00Z",
            "completed_at": "2026-05-15T11:00:00Z",
        },
    ]

    dataset = build_hr_recruiting_dataset(rows, now=now, config=_config())

    assert dataset["projection_mode"] == "read_only"
    assert dataset["pii_suppressed"] is True
    assert dataset["row_counts"]["source_rows"] == 4
    assert dataset["row_counts"]["deduped_leads"] == 3
    assert dataset["summary"] == {
        "active_leads": 2,
        "new_leads_today": 1,
        "avg_process_age_hours": 50.0,
        "stale_leads": 1,
        "completed_today": 1,
    }

    by_worklist = {row["worklist"]: row for row in dataset["by_worklist"]}
    assert by_worklist["Recruiter Review"]["avg_age_hours"] == 12.0
    assert by_worklist["Recruiter Review"]["stale_24h"] == 0
    assert by_worklist["Safety Review"]["max_age_hours"] == 72.0
    assert by_worklist["Safety Review"]["stale_24h"] == 1
    assert by_worklist["Safety Review"]["stale_48h"] == 1
    assert by_worklist["Safety Review"]["stale_72h"] == 1

    daily = {(row["date"], row["worklist"]): row for row in dataset["daily"]}
    assert daily[("2026-05-15", "Background Check")]["completed_leads"] == 1
    assert daily[("2026-05-15", "Background Check")]["avg_process_time_hours"] == 3.0

    trend = {row["date"]: row for row in dataset["trend"]}
    assert trend["2026-05-12"]["active_leads"] == 1
    assert trend["2026-05-12"]["stale_leads"] == 1
    assert trend["2026-05-14"]["avg_age_hours"] == 26.0

    serialized = json.dumps(dataset)
    assert "private.one@example.com" not in serialized
    assert "555-0100" not in serialized
    assert "123-45-6789" not in serialized
    assert "Private Applicant" not in serialized


def test_fallback_dedupe_hash_uses_applicant_worklist_and_assignment_time() -> None:
    now = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    rows = [
        {
            "applicant": "Private Applicant",
            "worklist": "Recruiter Review",
            "status": "Assigned",
            "first_assigned_at": "05/15/2026 08:00 AM",
        },
        {
            "applicant": "Private Applicant",
            "worklist": "Recruiter Review",
            "status": "Assigned",
            "first_assigned_at": "05/15/2026 08:00 AM",
        },
    ]

    dataset = build_hr_recruiting_dataset(rows, now=now, config=_config())

    assert dataset["row_counts"]["source_rows"] == 2
    assert dataset["row_counts"]["deduped_leads"] == 1
    assert dataset["summary"]["active_leads"] == 1
    assert dataset["summary"]["new_leads_today"] == 1


def test_empty_hr_recruiting_dataset_is_explicit_and_safe() -> None:
    now = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)

    dataset = build_hr_recruiting_dataset(
        [],
        now=now,
        config=_config(),
        source_status="snapshot_not_configured",
        source_message="Configure HR_RECRUITING_SNAPSHOT_URL.",
    )

    assert dataset["source_status"] == "snapshot_not_configured"
    assert dataset["summary"]["active_leads"] == 0
    assert dataset["by_worklist"] == []
    assert dataset["daily"] == []
    assert dataset["status_counts"] == []
    assert dataset["trend"] == []
    assert dataset["source_message"] == "Configure HR_RECRUITING_SNAPSHOT_URL."


def test_imported_hr_recruiting_state_feeds_dataset_without_pii(tmp_path) -> None:
    state_path = tmp_path / "hr-recruiting.json"
    result = import_hr_recruiting_snapshot(
        json.dumps(
            {
                "rows": [
                    {
                        "source_email_id": "outlook-message-1",
                        "applicant": "Private Applicant",
                        "worklist": "Recruiter Review",
                        "status": "Assigned",
                        "first_assigned_at": "2026-05-14T10:00:00Z",
                        "current_worklist_entered_at": "2026-05-15T00:00:00Z",
                        "email": "private@example.com",
                    }
                ]
            }
        ),
        filename="hr-recruiting.json",
        path=state_path,
    )

    assert result["status"] == "ok"
    assert result["row_count"] == 1
    dataset = asyncio.run(
        get_hr_recruiting_dataset(
            now=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
            config=HrRecruitingConfig(snapshot_path=str(state_path)),
        )
    )

    assert dataset["source_status"] == "ok"
    assert dataset["summary"]["active_leads"] == 1
    serialized = json.dumps(dataset)
    assert "private@example.com" not in serialized
    assert "Private Applicant" not in serialized


def test_hr_recruiting_import_dry_run_does_not_write(tmp_path) -> None:
    state_path = tmp_path / "hr-recruiting.json"
    result = import_hr_recruiting_snapshot(
        "source_email_id,applicant,worklist,status,first_assigned_at\nmsg-1,Private Applicant,Recruiter Review,Assigned,2026-05-14",
        filename="hr.csv",
        dry_run=True,
        path=state_path,
    )

    assert result["status"] == "ok"
    assert not state_path.exists()
