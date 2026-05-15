"""Tests for HR recruiting API and Power BI exports."""

from __future__ import annotations

import sys
import types
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Stub mygeotab so Power BI imports do not require the SDK in lean test envs.
if "mygeotab" not in sys.modules:
    fake = types.ModuleType("mygeotab")

    class _FakeAPI:
        def __init__(self, *a, **kw):
            pass

        def authenticate(self):
            pass

        def get(self, *a, **kw):
            return []

    fake.API = _FakeAPI
    sys.modules["mygeotab"] = fake

from routers import hr_recruiting, hr_recruiting_powerbi  # noqa: E402


def _dataset() -> dict:
    return {
        "generated_at": "2026-05-15T12:00:00+00:00",
        "projection_mode": "read_only",
        "source_system": "TenStreet Outlook/Zapier",
        "source_authority": "Zapier Table + approved TenStreet Outlook emails",
        "source": "zapier_table",
        "table_id": "01KR00WV4YHCB6BMYDE1EG7HEM",
        "source_status": "ok",
        "source_message": None,
        "pii_suppressed": True,
        "sla_hours": [24, 48, 72],
        "summary": {
            "active_leads": 2,
            "new_leads_today": 1,
            "avg_process_age_hours": 50.0,
            "stale_leads": 1,
            "completed_today": 1,
        },
        "by_worklist": [
            {
                "worklist": "Recruiter Review",
                "active_leads": 2,
                "new_leads_today": 1,
                "avg_age_hours": 12.0,
                "max_age_hours": 18.0,
                "stale_24h": 0,
                "stale_48h": 0,
                "stale_72h": 0,
            }
        ],
        "daily": [
            {
                "date": "2026-05-15",
                "worklist": "Recruiter Review",
                "new_leads": 1,
                "completed_leads": 1,
                "active_leads": 2,
                "avg_process_time_hours": 3.0,
            }
        ],
        "status_counts": [{"status": "Assigned", "count": 2}],
        "trend": [
            {
                "date": "2026-05-15",
                "active_leads": 2,
                "new_leads": 1,
                "stale_leads": 0,
                "avg_age_hours": 12.0,
            }
        ],
        "row_counts": {
            "source_rows": 2,
            "deduped_leads": 2,
            "active_leads": 2,
            "completed_leads": 0,
            "invalid_rows": 0,
            "source_email_dedupe_rows": 2,
        },
        "validation_errors": {},
    }


def _client(monkeypatch) -> TestClient:
    async def fake_dataset():
        return _dataset()

    monkeypatch.setattr(hr_recruiting, "get_hr_recruiting_dataset", fake_dataset)
    monkeypatch.setattr(hr_recruiting_powerbi, "get_hr_recruiting_dataset", fake_dataset)
    app = FastAPI()
    app.include_router(hr_recruiting.router, prefix="/api/hr-recruiting")
    app.include_router(hr_recruiting_powerbi.router, prefix="/api/powerbi")
    return TestClient(app)


def test_hr_recruiting_worklist_endpoint_returns_read_only_dataset(monkeypatch) -> None:
    response = _client(monkeypatch).get("/api/hr-recruiting/worklist")

    assert response.status_code == 200
    payload = response.json()
    assert payload["projection_mode"] == "read_only"
    assert payload["summary"]["active_leads"] == 2
    assert payload["pii_suppressed"] is True
    assert "phone" not in str(payload).lower()
    assert "ssn" not in str(payload).lower()


def test_hr_recruiting_powerbi_tables_include_export_metadata(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.get("/api/powerbi/hr-recruiting/by-worklist")

    assert response.status_code == 200
    rows = response.json()
    assert rows[0]["connection_name"] == "hr_recruiting_by_worklist"
    assert rows[0]["projection_mode"] == "read_only"
    assert rows[0]["source_authority"] == "Zapier Table + approved TenStreet Outlook emails"
    assert rows[0]["worklist"] == "Recruiter Review"


def test_hr_recruiting_powerbi_snapshot_has_required_tables(monkeypatch) -> None:
    response = _client(monkeypatch).get("/api/powerbi/hr-recruiting-snapshot")

    assert response.status_code == 200
    payload = response.json()
    assert payload["connection_name"] == "hr_recruiting_snapshot"
    assert payload["summary"]["completed_today"] == 1
    assert payload["by_worklist"][0]["stale_24h"] == 0
    assert payload["status_counts"][0]["status"] == "Assigned"
