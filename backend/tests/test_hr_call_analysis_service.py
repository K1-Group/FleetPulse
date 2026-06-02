"""Tests for HR call-analysis imports and dashboard-safe metrics."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from configs.hr_call_analysis import HrCallAnalysisConfig  # noqa: E402
from services.hr_call_analysis_service import (  # noqa: E402
    get_department_call_analysis_dataset,
    get_hr_call_analysis_dataset,
    import_hr_call_analysis_snapshot,
)


def _config(path: str = "/tmp/hr-call-analysis-test.json") -> HrCallAnalysisConfig:
    return HrCallAnalysisConfig(
        state_path=path,
        import_api_key="",
        hash_salt="fleetpulse-hr-call",
        active_extensions=("702", "722", "725", "728", "700"),
        sharepoint_enabled=False,
        sharepoint_folder_url="",
        graph_tenant_id="",
        graph_client_id="",
        graph_client_secret="",
        site_id="",
        site_url="https://tenant.sharepoint.com/sites/K1",
        site_hostname="tenant.sharepoint.com",
        site_path="/sites/K1",
        drive_id="",
        drive_name="",
        folder_path="Grasshopper/Call Analysis Reports/HR",
        source_file_urls=(),
        file_extensions=(".txt",),
        file_limit=25,
        sync_api_key="",
        sync_interval_minutes=15,
        timeout_seconds=5,
        retry_count=0,
        retry_backoff_seconds=0,
        departments=("Operations", "HR", "Maintenance"),
        department_folder_paths={},
    )


def test_hr_call_analysis_sharepoint_default_includes_csv(monkeypatch) -> None:
    monkeypatch.delenv("HR_CALL_ANALYSIS_SHAREPOINT_FILE_EXTENSIONS", raising=False)

    config = HrCallAnalysisConfig.from_env()

    assert config.file_extensions == (".txt", ".csv")


def test_call_analysis_dataset_suppresses_phone_and_scores_employee(tmp_path) -> None:
    config = _config(str(tmp_path / "hr-call-analysis.json"))
    rows = [
        {
            "Date/Time": "5/8/2026 9:16:31 PM",
            "VPS Number": "(855) 558-1118",
            "Duration": '="5:36"',
            "Caller ID": "(580) 748-2358",
            "Connecting #": "Unknown",
            "Extension": "702 - David Attar",
            "Direction": "In",
            "Type": "Inbound leg of forwarded call",
        },
        {
            "Date/Time": "5/8/2026 9:16:48 PM",
            "VPS Number": "(855) 558-1118",
            "Duration": '="5:06"',
            "Caller ID": "Unknown",
            "Connecting #": "(580) 748-2358",
            "Extension": "702 - David Attar",
            "Direction": "Out",
            "Type": "Forwarded call connected",
        },
    ]

    result = import_hr_call_analysis_snapshot(
        json.dumps({"call_rows": rows}),
        filename="call.json",
        config=config,
    )
    assert result["status"] == "ok"
    assert result["call_rows"] == 2
    dataset = asyncio.run(get_hr_call_analysis_dataset(config=config))

    assert dataset["summary"]["total_call_legs"] == 2
    assert dataset["summary"]["inbound_calls"] == 1
    assert dataset["summary"]["outbound_attempts"] == 1
    assert dataset["summary"]["connected_calls"] == 1
    assert dataset["summary"]["total_call_legs"] == (
        dataset["summary"]["inbound_calls"] + dataset["summary"]["outbound_attempts"]
    )
    assert dataset["employee_productivity"][0]["employee_name"] == "David Attar"
    assert dataset["employee_productivity"][0]["inbound_legs"] == 1
    assert dataset["employee_productivity"][0]["outbound_legs"] == 1
    serialized = json.dumps(dataset)
    assert "(855) 558-1118" not in serialized
    assert "(580) 748-2358" not in serialized


def test_legacy_call_state_infers_direction_flags(tmp_path) -> None:
    state_path = tmp_path / "hr-call-analysis.json"
    config = _config(str(state_path))
    state_path.write_text(
        json.dumps(
            {
                "call_rows": [
                    {
                        "call_id": "legacy-inbound",
                        "department": "HR",
                        "department_key": "hr",
                        "call_started_at": "2026-05-31T09:00:00Z",
                        "call_date": "2026-05-31",
                        "month": "2026-05",
                        "extension_id": "702",
                        "employee_name": "David Attar",
                        "direction": "In",
                        "call_type": "Inbound leg of forwarded call",
                        "duration_seconds": 120,
                        "is_outbound_attempt": 1,
                    },
                    {
                        "call_id": "legacy-outbound",
                        "department": "HR",
                        "department_key": "hr",
                        "call_started_at": "2026-05-31T09:05:00Z",
                        "call_date": "2026-05-31",
                        "month": "2026-05",
                        "extension_id": "702",
                        "employee_name": "David Attar",
                        "direction": "Out",
                        "call_type": "Mobile Outbound Connected",
                        "duration_seconds": 180,
                        "is_outbound_attempt": 1,
                    },
                ],
                "analysis_reports": [],
                "lead_rows": [],
                "activity_rows": [],
            }
        ),
        encoding="utf-8",
    )

    dataset = asyncio.run(
        get_department_call_analysis_dataset(
            department="HR",
            config=config,
            start_date="2026-05-31",
            end_date="2026-05-31",
        )
    )

    assert dataset["summary"]["total_call_legs"] == 2
    assert dataset["summary"]["inbound_calls"] == 1
    assert dataset["summary"]["outbound_attempts"] == 1
    assert dataset["daily_volume"][0]["call_legs"] == 2
    assert dataset["daily_volume"][0]["inbound_calls"] == 1
    assert dataset["daily_volume"][0]["outbound_attempts"] == 1
    assert dataset["employee_productivity"][0]["inbound_legs"] == 1
    assert dataset["employee_productivity"][0]["outbound_legs"] == 1


def test_hr_call_analysis_filters_department_totals_to_active_extensions(tmp_path) -> None:
    config = _config(str(tmp_path / "hr-call-analysis.json"))
    result = import_hr_call_analysis_snapshot(
        json.dumps(
            {
                "call_rows": [
                    {
                        "Date/Time": "5/29/2026 10:05:22 AM",
                        "VPS Number": "(855) 558-1118",
                        "Duration": '="2:00"',
                        "Caller ID": "Unknown",
                        "Connecting #": "Unknown",
                        "Extension": "702 - David Attar",
                        "Direction": "Out",
                        "Type": "Mobile Outbound Connected",
                    },
                    {
                        "Date/Time": "5/29/2026 10:06:22 AM",
                        "VPS Number": "(855) 558-1118",
                        "Duration": '="2:00"',
                        "Caller ID": "Unknown",
                        "Connecting #": "Unknown",
                        "Extension": "999 - Non HR Agent",
                        "Direction": "Out",
                        "Type": "Mobile Outbound Connected",
                    },
                ]
            }
        ),
        filename="Detail_05.29.csv",
        config=config,
    )

    assert result["status"] == "ok"
    dataset = asyncio.run(
        get_hr_call_analysis_dataset(
            config=config,
            start_date="2026-05-29",
            end_date="2026-05-29",
        )
    )

    assert dataset["summary"]["total_call_legs"] == 1
    assert dataset["summary"]["outbound_attempts"] == 1
    assert dataset["row_counts"]["unfiltered_call_rows"] == 1
    assert dataset["employee_productivity"][0]["extension_id"] == "702"
    assert "Non HR Agent" not in json.dumps(dataset)


def test_imported_state_feeds_dataset_and_first_call_sla(tmp_path) -> None:
    state_path = tmp_path / "hr-call-analysis.json"
    config = _config(str(state_path))
    phone_hash = "candidate-phone-hash"
    result = import_hr_call_analysis_snapshot(
        json.dumps(
            {
                "call_rows": [
                    {
                        "call_started_at": "2026-05-02T09:00:00Z",
                        "extension_id": "702",
                        "employee_name": "David Attar",
                        "direction": "In",
                        "call_type": "Mobile Inbound",
                        "duration_seconds": 120,
                        "external_party_hash": phone_hash,
                    },
                    {
                        "call_started_at": "2026-05-02T10:00:00Z",
                        "extension_id": "702",
                        "employee_name": "David Attar",
                        "direction": "Out",
                        "call_type": "Mobile Outbound Connected",
                        "duration_seconds": 300,
                        "external_party_hash": phone_hash,
                    }
                ],
                "lead_rows": [
                    {
                        "source_email_id": "message-1",
                        "phone_hash": phone_hash,
                        "worklist": "DFW",
                        "status": "Assigned",
                        "first_assigned_at": "2026-05-02T08:00:00Z",
                    }
                ],
            }
        ),
        filename="hr-call.json",
        config=config,
    )

    assert result["status"] == "ok"
    dataset = asyncio.run(
        get_hr_call_analysis_dataset(
            now=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
            config=config,
        )
    )

    assert dataset["source_status"] == "ok"
    assert dataset["summary"]["total_call_legs"] == 2
    assert dataset["summary"]["inbound_calls"] == 1
    assert dataset["summary"]["outbound_attempts"] == 1
    assert dataset["summary"]["first_call_eligible_leads"] == 1
    assert dataset["summary"]["first_call_within_24h"] == 1
    assert dataset["follow_up"][0]["total_call_legs"] == 2
    assert dataset["follow_up"][0]["inbound_calls"] == 1
    assert dataset["follow_up"][0]["outbound_attempts"] == 1
    assert dataset["employee_productivity"][0]["employee_name"] == "David Attar"
    assert "(580)" not in json.dumps(dataset)


def test_teams_onboarding_lead_rows_match_grasshopper_calls_by_hashed_phone(tmp_path) -> None:
    state_path = tmp_path / "hr-call-analysis.json"
    config = _config(str(state_path))
    result = import_hr_call_analysis_snapshot(
        json.dumps(
            {
                "call_rows": [
                    {
                        "Date/Time": "5/29/2026 11:00:00 AM",
                        "Caller ID": "(214) 555-0199",
                        "Connecting #": "Unknown",
                        "Extension": "728 - Jordan Teague",
                        "Direction": "In",
                        "Type": "Mobile Inbound",
                        "Duration": '="2:00"',
                    },
                    {
                        "Date/Time": "5/29/2026 12:00:00 PM",
                        "Caller ID": "Unknown",
                        "Connecting #": "(214) 555-0199",
                        "Extension": "728 - Jordan Teague",
                        "Direction": "Out",
                        "Type": "Mobile Outbound Connected",
                        "Duration": '="3:00"',
                    },
                ],
                "lead_rows": [
                    {
                        "LeadKeyValue": "teams-lead-1",
                        "LeadPhone": "(214) 555-0199",
                        "WorklistName": "Onboarding Drivers",
                        "TenstreetStatus": "New",
                        "ReceivedAtUTC": "2026-05-29T10:00:00Z",
                    }
                ],
            }
        ),
        filename="teams-lead-and-detail.json",
        config=config,
    )

    assert result["status"] == "ok"
    dataset = asyncio.run(
        get_hr_call_analysis_dataset(
            now=datetime(2026, 5, 30, tzinfo=timezone.utc),
            config=config,
            start_date="2026-05-29",
            end_date="2026-05-29",
        )
    )

    assert dataset["summary"]["total_call_legs"] == 2
    assert dataset["summary"]["inbound_calls"] == 1
    assert dataset["summary"]["outbound_attempts"] == 1
    assert dataset["summary"]["follow_up_count"] == 1
    assert dataset["summary"]["first_call_within_24h"] == 1
    assert dataset["follow_up"][0]["worklist"] == "Onboarding Drivers"
    assert dataset["follow_up"][0]["status"] == "New"
    assert dataset["follow_up"][0]["total_call_legs"] == 2
    assert dataset["follow_up"][0]["inbound_calls"] == 1
    assert dataset["follow_up"][0]["outbound_attempts"] == 1
    serialized = json.dumps(dataset)
    assert "(214) 555-0199" not in serialized
    assert "LeadPhone" not in serialized


def test_department_call_analysis_filters_selected_date_range_and_compares_previous(tmp_path) -> None:
    state_path = tmp_path / "department-call-analysis.json"
    config = _config(str(state_path))
    result = import_hr_call_analysis_snapshot(
        json.dumps(
            {
                "call_rows": [
                    {
                        "department": "HR",
                        "call_started_at": "2026-05-10T10:00:00Z",
                        "extension_id": "702",
                        "employee_name": "David Attar",
                        "direction": "Out",
                        "call_type": "Mobile Outbound Connected",
                        "duration_seconds": 120,
                        "external_party_hash": "candidate-current",
                    },
                    {
                        "department": "HR",
                        "call_started_at": "2026-05-03T10:00:00Z",
                        "extension_id": "702",
                        "employee_name": "David Attar",
                        "direction": "Out",
                        "call_type": "Mobile Outbound Connected",
                        "duration_seconds": 60,
                        "external_party_hash": "candidate-previous",
                    },
                ],
                "lead_rows": [
                    {
                        "department": "HR",
                        "lead_key": "lead-current",
                        "phone_hash": "candidate-current",
                        "first_assigned_at": "2026-05-10T08:00:00Z",
                    },
                    {
                        "department": "HR",
                        "lead_key": "lead-previous",
                        "phone_hash": "candidate-previous",
                        "first_assigned_at": "2026-05-03T08:00:00Z",
                    },
                ],
            }
        ),
        filename="department-calls.json",
        config=config,
    )
    assert result["status"] == "ok"

    dataset = asyncio.run(
        get_department_call_analysis_dataset(
            config=config,
            department="HR",
            now=datetime(2026, 5, 11, tzinfo=timezone.utc),
            start_date="2026-05-10",
            end_date="2026-05-10",
        )
    )

    assert dataset["date_range"]["start"] == "2026-05-10"
    assert dataset["summary"]["total_call_legs"] == 1
    assert dataset["summary"]["answered_calls"] == 1
    assert dataset["summary"]["follow_up_count"] == 1
    assert dataset["trend_comparison"]["previous"]["call_volume"] == 0
    assert dataset["daily_volume"] == [
        {
            "date": "2026-05-10",
            "call_legs": 1,
            "inbound_calls": 0,
            "outbound_attempts": 1,
            "connected_calls": 1,
            "voicemails": 0,
            "total_minutes": 2.0,
        }
    ]


def test_department_call_analysis_filters_activity_by_single_day_through_may_31(tmp_path) -> None:
    state_path = tmp_path / "department-call-analysis.json"
    config = _config(str(state_path))
    result = import_hr_call_analysis_snapshot(
        json.dumps(
            {
                "call_rows": [
                    {
                        "department": "HR",
                        "call_started_at": "2026-05-30T10:00:00Z",
                        "extension_id": "702",
                        "employee_name": "HR Agent",
                        "direction": "Out",
                        "call_type": "Mobile Outbound Connected",
                        "duration_seconds": 60,
                    },
                    {
                        "department": "HR",
                        "call_started_at": "2026-05-31T11:00:00Z",
                        "extension_id": "702",
                        "employee_name": "HR Agent",
                        "direction": "Out",
                        "call_type": "Mobile Outbound Connected",
                        "duration_seconds": 180,
                    },
                    {
                        "call_started_at": "2026-05-31T12:00:00Z",
                        "extension_id": "1",
                        "employee_name": "Customer Operations Manager",
                        "direction": "Out",
                        "call_type": "Mobile Outbound Connected",
                        "duration_seconds": 240,
                    },
                ]
            }
        ),
        filename="Detail_05.31.2026.csv",
        config=config,
    )
    assert result["status"] == "ok"

    dataset = asyncio.run(
        get_department_call_analysis_dataset(
            config=config,
            department="HR",
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
            start_date="2026-05-31",
            end_date="2026-05-31",
        )
    )

    assert dataset["date_range"]["start"] == "2026-05-31"
    assert dataset["date_range"]["end"] == "2026-05-31"
    assert dataset["summary"]["total_call_legs"] == 1
    assert dataset["summary"]["total_minutes"] == 3.0
    assert dataset["daily_volume"] == [
        {
            "date": "2026-05-31",
            "call_legs": 1,
            "inbound_calls": 0,
            "outbound_attempts": 1,
            "connected_calls": 1,
            "voicemails": 0,
            "total_minutes": 3.0,
        }
    ]

    operations = asyncio.run(
        get_department_call_analysis_dataset(
            config=config,
            department="Operations",
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
            start_date="2026-05-31",
            end_date="2026-05-31",
        )
    )
    assert operations["summary"]["total_call_legs"] == 1
    assert operations["summary"]["total_minutes"] == 4.0


def test_hr_total_calls_kpi_uses_date_scoped_detail_rows_not_monthly_activity(tmp_path) -> None:
    config = _config(str(tmp_path / "hr-call-analysis.json"))
    result = import_hr_call_analysis_snapshot(
        json.dumps(
            {
                "call_rows": [
                    {
                        "Date/Time": "5/31/2026 10:00:00 AM",
                        "Extension": "702 - David Attar",
                        "Direction": "Out",
                        "Type": "Mobile Outbound Connected",
                        "Duration": '="1:00"',
                    },
                    {
                        "Date/Time": "5/31/2026 10:01:00 AM",
                        "Extension": "702 - David Attar",
                        "Direction": "In",
                        "Type": "Mobile Inbound",
                        "Duration": '="1:00"',
                    },
                    {
                        "Date/Time": "5/31/2026 10:02:00 AM",
                        "Extension": "722 - Hamzeh Alghanem",
                        "Direction": "Out",
                        "Type": "Mobile Outbound Connected",
                        "Duration": '="1:00"',
                    },
                    {
                        "Date/Time": "5/31/2026 10:03:00 AM",
                        "Extension": "722 - Hamzeh Alghanem",
                        "Direction": "In",
                        "Type": "Mobile Inbound",
                        "Duration": '="1:00"',
                    },
                    {
                        "Date/Time": "5/31/2026 10:04:00 AM",
                        "Extension": "700 - Karina Nunez",
                        "Direction": "Out",
                        "Type": "Mobile Outbound Connected",
                        "Duration": '="1:00"',
                    },
                    {
                        "Date/Time": "5/31/2026 10:05:00 AM",
                        "Extension": "728 - Jordan Teague",
                        "Direction": "In",
                        "Type": "Inbound leg of forwarded call",
                        "Duration": '="1:00"',
                    },
                    {
                        "Date/Time": "5/31/2026 10:06:00 AM",
                        "Extension": "4 - HR Manager",
                        "Direction": "In",
                        "Type": "Mobile Inbound",
                        "Duration": '="1:00"',
                    },
                ],
                "activity_rows": [
                    {
                        "report_date": "2026-05-31",
                        "activity_period": "May 2026",
                        "extension_id": "702",
                        "employee_name": "David Attar",
                        "activity_calls": 564,
                    },
                    {
                        "report_date": "2026-05-31",
                        "activity_period": "May 2026",
                        "extension_id": "722",
                        "employee_name": "Hamzeh Alghanem",
                        "activity_calls": 675,
                    },
                    {
                        "report_date": "2026-05-31",
                        "activity_period": "May 2026",
                        "extension_id": "700",
                        "employee_name": "Karina Nunez",
                        "activity_calls": 69,
                    },
                    {
                        "report_date": "2026-05-31",
                        "activity_period": "May 2026",
                        "extension_id": "725",
                        "employee_name": "Leen Ababneh",
                        "activity_calls": 394,
                    },
                    {
                        "report_date": "2026-05-31",
                        "activity_period": "May 2026",
                        "extension_id": "728",
                        "employee_name": "Jordan Teague",
                        "activity_calls": 73,
                    },
                    {
                        "report_date": "2026-05-31",
                        "activity_period": "May 2026",
                        "extension_id": "4",
                        "employee_name": "HR Manager",
                        "activity_calls": 84,
                    },
                ],
            }
        ),
        filename="Detail_05.31.2026.json",
        config=config,
    )

    assert result["status"] == "ok"
    dataset = asyncio.run(
        get_hr_call_analysis_dataset(
            config=config,
            start_date="2026-05-31",
            end_date="2026-05-31",
        )
    )

    assert dataset["active_extensions"] == ["702", "722", "725", "728", "700"]
    assert dataset["summary"]["total_call_legs"] == 6
    assert dataset["summary"]["inbound_calls"] == 3
    assert dataset["summary"]["outbound_attempts"] == 3
    assert dataset["summary"]["total_call_legs"] == (
        dataset["summary"]["inbound_calls"] + dataset["summary"]["outbound_attempts"]
    )
    assert dataset["summary"]["activity_calls"] == 1775
    assert dataset["row_counts"]["call_rows"] == 6


def test_department_call_analysis_uses_activity_summary_for_department_call_counts(tmp_path) -> None:
    state_path = tmp_path / "department-call-analysis.json"
    config = _config(str(state_path))
    activity_csv = """Report: Activity_05.31.2026
Numbers and Extensions,Voice Mails / Calls / Ratio,Hangups / Calls / Ratio,Faxes / Calls / Ratio,Voice calls / Calls / Ratio
May 2026
Totals,357/6930/5%,508/6930/7%,2/6930/0%,6063/6930/87%
Phone numbers
(855) 558-1118,356/6896/5%,499/6896/7%,2/6896/0%,6039/6896/88%
Extensions
1 - Customer Operations Manager,130/1312/10%,23/1312/2%,0/1312/0%,1159/1312/88%
4 - HR Manager ,21/84/25%,3/84/4%,0/84/0%,60/84/71%
702 - David Attar,72/564/13%,1/564/0%,0/564/0%,491/564/87%
722 - Hamzeh Alghanem,8/675/1%,0/675/0%,0/675/0%,667/675/99%
725 - Yara Azzouqah,11/394/3%,0/394/0%,0/394/0%,383/394/97%
728 - HR Team Member,1/73/1%,0/73/0%,0/73/0%,72/73/99%
"""

    result = import_hr_call_analysis_snapshot(
        activity_csv,
        filename="Activity_05.31.2026.csv",
        config=config,
    )

    assert result["status"] == "ok"
    assert result["activity_rows"] == 6

    hr = asyncio.run(
        get_department_call_analysis_dataset(
            config=config,
            department="HR",
            start_date="2026-05-31",
            end_date="2026-05-31",
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
    )
    operations = asyncio.run(
        get_department_call_analysis_dataset(
            config=config,
            department="Operations",
            start_date="2026-05-31",
            end_date="2026-05-31",
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
    )

    assert hr["summary"]["activity_calls"] == 1706
    assert hr["summary"]["activity_report_date"] == "2026-05-31"
    assert hr["summary"]["activity_period"] == "May 2026"
    assert hr["summary"]["total_call_legs"] == 0
    assert operations["summary"]["activity_calls"] == 1312


def test_sharepoint_analysis_report_parses_coaching_flag(tmp_path) -> None:
    state_path = tmp_path / "hr-call-analysis.json"
    config = _config(str(state_path))
    content = """Analysis Report:

CALL INTELLIGENCE REPORT

BASIC INFORMATION
- File Name: 05-20-2026- (817) 807-2272-HR Manager-10-41 AM.mp3
- Date & Time: 2026-05-21T09:20:06Z
- Agent Name: Ruth
- Call Duration: Short
- Language: English

PRIMARY ISSUE CATEGORY
[x] Other: Driver recruiting follow-up

HUMAN ERRORS DETECTED
No errors detected.

CUSTOMER SENTIMENT ANALYSIS
- Overall Sentiment: Positive

RESOLUTION ASSESSMENT
- Was the issue resolved? Yes
- Resolution Quality: Good

URGENT FLAGS
- Urgent: NO

ACTION ITEMS
[ ] Follow up with applicant -> Owner: Ruth -> Due: ASAP
"""

    result = import_hr_call_analysis_snapshot(
        content,
        filename="05-20-2026- (817) 807-2272-HR Manager-10-41 AM.mp3)-analysis.txt",
        config=config,
    )
    assert result["analysis_reports"] == 1
    dataset = asyncio.run(get_hr_call_analysis_dataset(config=config))
    assert dataset["summary"]["analysis_reports"] == 1
    assert dataset["summary"]["coaching_flags"] == 1
    serialized = json.dumps(dataset)
    assert "(817) 807-2272" not in serialized


def test_department_call_analysis_filters_rows_by_department(tmp_path) -> None:
    state_path = tmp_path / "department-call-analysis.json"
    config = _config(str(state_path))

    result = import_hr_call_analysis_snapshot(
        json.dumps(
            {
                "call_rows": [
                    {
                        "department": "Ops",
                        "call_started_at": "2026-05-02T10:00:00Z",
                        "extension_id": "810",
                        "employee_name": "Ops Agent",
                        "direction": "Out",
                        "call_type": "Mobile Outbound Connected",
                        "duration_seconds": 180,
                        "external_party_hash": "ops-party",
                    },
                    {
                        "department": "Maintenance",
                        "call_started_at": "2026-05-02T11:00:00Z",
                        "extension_id": "820",
                        "employee_name": "Shop Agent",
                        "direction": "Out",
                        "call_type": "Mobile Outbound Connected",
                        "duration_seconds": 420,
                        "external_party_hash": "shop-party",
                    },
                ],
                "analysis_reports": [
                    {
                        "department": "Maintenance",
                        "filename": "maintenance-analysis.txt",
                        "content": "CALL INTELLIGENCE REPORT\n- Agent Name: Shop Agent\n- Overall Sentiment: Negative\n- Urgent: YES",
                    }
                ],
            }
        ),
        filename="department-calls.json",
        config=config,
    )
    assert result["status"] == "ok"

    ops = asyncio.run(get_hr_call_analysis_dataset(config=config, now=datetime(2026, 5, 3, tzinfo=timezone.utc)))
    all_departments = asyncio.run(
        get_department_call_analysis_dataset(
            config=config,
            department="All",
            now=datetime(2026, 5, 3, tzinfo=timezone.utc),
        )
    )
    maintenance = asyncio.run(
        get_department_call_analysis_dataset(
            config=config,
            department="Maintenance",
            now=datetime(2026, 5, 3, tzinfo=timezone.utc),
        )
    )

    assert ops["department"] == "HR"
    assert ops["summary"]["total_call_legs"] == 0
    assert all_departments["summary"]["total_call_legs"] == 2
    assert "Operations" in all_departments["configured_departments"]
    assert maintenance["summary"]["total_call_legs"] == 1
    assert maintenance["summary"]["coaching_flags"] == 1
