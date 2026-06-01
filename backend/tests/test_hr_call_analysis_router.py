"""Tests for HR call-analysis API and Power BI exports."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from routers import department_call_analysis, hr_call_analysis, hr_call_analysis_powerbi  # noqa: E402


def _dataset() -> dict:
    return {
        "generated_at": "2026-05-21T12:00:00+00:00",
        "projection_mode": "read_only",
        "source_system": "Grasshopper / Microsoft SharePoint",
        "source_authority": "Grasshopper call logs + SharePoint HR call-analysis reports",
        "department": "HR",
        "department_key": "hr",
        "source_status": "ok",
        "source_message": None,
        "last_imported_at": "2026-05-21T12:00:00+00:00",
        "pii_suppressed": True,
        "phone_numbers_stored": False,
        "active_extensions": ["4", "702", "722", "725"],
        "coverage": {"start": "2026-03-01T00:00:00Z", "end": "2026-05-08T00:00:00Z", "months": ["2026-03"]},
        "summary": {
            "total_call_legs": 2,
            "total_minutes": 10.0,
            "avg_call_seconds": 300,
            "outbound_attempts": 1,
            "connected_calls": 1,
            "connect_rate_pct": 100.0,
            "voicemails": 0,
            "hangups": 0,
            "active_employee_count": 1,
            "analysis_reports": 1,
            "coaching_flags": 1,
            "urgent_flags": 0,
            "unresolved_calls": 0,
            "human_error_reports": 0,
            "first_call_eligible_leads": 1,
            "first_call_within_24h": 1,
            "first_call_24h_pct": 1.0,
            "stale_no_call_48h": 0,
        },
        "employee_productivity": [
            {
                "extension_id": "702",
                "employee_name": "David Attar",
                "productivity_score_0_100": 90.0,
                "call_legs": 2,
                "voice_call_legs": 2,
                "distinct_external_parties": 1,
                "total_minutes": 10.0,
                "outbound_legs": 1,
                "connected_legs": 1,
                "not_connected_legs": 0,
                "voicemails": 0,
                "hangups": 0,
                "connected_rate_pct": 50.0,
                "voicemail_rate_pct": 0.0,
                "hangup_rate_pct": 0.0,
            }
        ],
        "monthly_employee_productivity": [],
        "daily_volume": [],
        "follow_up": [],
        "coaching_flags": [
            {
                "analysis_file_key": "analysis-key",
                "call_date": "2026-05-20",
                "agent_name": "Ruth",
                "category": "Driver recruiting follow-up",
                "sentiment": "Positive",
                "resolved": True,
                "resolution_quality": "Good",
                "action_items_count": 1,
                "flag_reasons": "action_item",
            }
        ],
        "row_counts": {"call_rows": 2, "analysis_reports": 1},
        "validation_notes": [],
        "configured_departments": ["Operations", "HR", "Maintenance"],
        "department_rollups": [],
    }


def _client(monkeypatch) -> TestClient:
    async def fake_dataset(**kwargs):
        return _dataset()

    async def fake_department_dataset(department=None, **kwargs):
        payload = _dataset()
        payload["department"] = department or "All"
        payload["source_authority"] = "Grasshopper call logs + SharePoint department call-analysis reports"
        return payload

    monkeypatch.setattr(hr_call_analysis, "get_hr_call_analysis_dataset", fake_dataset)
    monkeypatch.setattr(hr_call_analysis_powerbi, "get_hr_call_analysis_dataset", fake_dataset)
    monkeypatch.setattr(department_call_analysis, "get_department_call_analysis_dataset", fake_department_dataset)
    app = FastAPI()
    app.include_router(hr_call_analysis.router, prefix="/api/hr-call-analysis")
    app.include_router(department_call_analysis.router, prefix="/api/department-call-analysis")
    app.include_router(hr_call_analysis_powerbi.router, prefix="/api/powerbi")
    return TestClient(app)


def test_hr_call_analysis_dashboard_returns_read_only_dataset(monkeypatch) -> None:
    response = _client(monkeypatch).get("/api/hr-call-analysis/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["projection_mode"] == "read_only"
    assert payload["pii_suppressed"] is True
    assert payload["phone_numbers_stored"] is False
    assert payload["summary"]["total_call_legs"] == 2


def test_department_call_analysis_dashboard_filters_by_department(monkeypatch) -> None:
    response = _client(monkeypatch).get("/api/department-call-analysis/dashboard?department=Maintenance")

    assert response.status_code == 200
    payload = response.json()
    assert payload["projection_mode"] == "read_only"
    assert payload["department"] == "Maintenance"
    assert payload["source_authority"] == "Grasshopper call logs + SharePoint department call-analysis reports"


def test_hr_call_analysis_import_endpoint_is_key_protected(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HR_CALL_ANALYSIS_STATE_PATH", str(tmp_path / "hr-call.json"))
    monkeypatch.setenv("HR_CALL_ANALYSIS_IMPORT_API_KEY", "expected")
    client = _client(monkeypatch)

    denied = client.post(
        "/api/hr-call-analysis/import",
        json={
            "filename": "call.csv",
            "content": "call_started_at,extension_id,employee_name,direction,call_type,duration_seconds,external_party_hash\n2026-05-02T10:00:00Z,702,David Attar,Out,Mobile Outbound Connected,300,hash",
        },
    )
    assert denied.status_code == 401

    ok = client.post(
        "/api/hr-call-analysis/import",
        headers={"X-FleetPulse-HR-Call-Key": "expected"},
        json={
            "filename": "call.csv",
            "content": "call_started_at,extension_id,employee_name,direction,call_type,duration_seconds,external_party_hash\n2026-05-02T10:00:00Z,702,David Attar,Out,Mobile Outbound Connected,300,hash",
        },
    )
    assert ok.status_code == 200
    assert ok.json()["call_rows"] == 1


def test_hr_call_analysis_powerbi_snapshot(monkeypatch) -> None:
    response = _client(monkeypatch).get("/api/powerbi/hr-call-analysis-snapshot")

    assert response.status_code == 200
    payload = response.json()
    assert payload["connection_name"] == "hr_call_analysis_snapshot"
    assert payload["summary"]["connect_rate_pct"] == 100.0
    assert payload["employee_productivity"][0]["employee_name"] == "David Attar"
