"""Tests for restored read-only Control Tower projections."""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

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

from models import Alert, AlertSeverity, ControlTowerTrailerTrackingResponse  # noqa: E402
from routers import control_tower  # noqa: E402
from services import control_tower_service  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(control_tower.router, prefix="/api/control-tower")
    return TestClient(app)


def test_attention_projects_live_alerts_without_fake_counts(monkeypatch):
    monkeypatch.setattr(
        control_tower_service,
        "get_recent_alerts",
        lambda hours=24: [
            Alert(
                id="a1",
                vehicle_id="v1",
                vehicle_name="219",
                alert_type="speeding",
                severity=AlertSeverity.HIGH,
                message="Speeding detected on 219",
                timestamp=datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc),
            )
        ],
    )
    monkeypatch.setattr(control_tower_service, "get_monitor_alerts", lambda limit=50: [])
    monkeypatch.setattr(control_tower_service, "get_monitor_status", lambda: {"running": False})

    response = _client().get("/api/control-tower/attention")

    assert response.status_code == 200
    payload = response.json()
    assert payload["projection_mode"] == "read_only"
    assert payload["items"][0]["source_authority"] == "Geotab"
    assert payload["items"][0]["action"] == "Review"
    assert any(feed["name"] == "Xcelerator route SLA feed" for feed in payload["feeds"])


def test_attention_projects_xcelerator_feed_rows(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_XCELERATOR_EVENT_FEED_URL", "https://example.invalid/xcelerator")
    monkeypatch.setattr(control_tower_service, "get_recent_alerts", lambda hours=24: [])
    monkeypatch.setattr(control_tower_service, "get_monitor_alerts", lambda limit=50: [])
    monkeypatch.setattr(control_tower_service, "get_monitor_status", lambda: {"running": False})
    monkeypatch.setattr(
        control_tower_service,
        "_fetch_xcelerator_event_rows",
        lambda: (
            [
                {
                    "event_type": "route_eta_exception_evaluated",
                    "message": "Route ROUTE-901 missed ETA threshold",
                    "route_id": "ROUTE-901",
                    "status": "exception",
                    "timestamp": "2026-05-16T12:30:00Z",
                }
            ],
            datetime(2026, 5, 16, 12, 30, tzinfo=timezone.utc),
        ),
    )

    response = _client().get("/api/control-tower/attention")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["source_authority"] == "K1 Group LLC / Xcelerator"
    assert payload["items"][0]["category"] == "Linehaul"
    assert payload["items"][0]["message"] == "Route ROUTE-901 missed ETA threshold"
    xcelerator_feed = next(feed for feed in payload["feeds"] if feed["name"] == "Xcelerator route SLA feed")
    assert xcelerator_feed["status"] == "healthy"
    assert "Read 1 Xcelerator event row" in xcelerator_feed["message"]


def test_financial_surface_is_k1_group_read_only_and_awaits_feed(monkeypatch):
    monkeypatch.delenv("FLEETPULSE_FINANCIAL_FEED_ENABLED", raising=False)
    monkeypatch.delenv("FLEETPULSE_QBO_FINANCIAL_FEED_URL", raising=False)

    response = _client().get("/api/control-tower/financial")

    assert response.status_code == 200
    payload = response.json()
    assert payload["projection_mode"] == "read_only"
    assert payload["source_authority"] == "K1 Group LLC / Xcelerator / QuickBooks"
    assert payload["accounts_payable"]["pending_amount"] is None
    assert payload["feeds"][0]["status"] == "awaiting_feed"


def test_configured_xcelerator_feed_url_reads_live_rows_without_fake_values(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_FINANCIAL_FEED_ENABLED", "true")
    monkeypatch.setenv("FLEETPULSE_XCELERATOR_EVENT_FEED_URL", "https://example.invalid/xcelerator")
    monkeypatch.setenv("FLEETPULSE_QBO_FINANCIAL_FEED_URL", "https://example.invalid/qbo")
    monkeypatch.setattr(
        control_tower_service,
        "get_qbo_financial_snapshot",
        lambda: {
            "status": "healthy",
            "message": "Read 1 QBO financial row.",
            "source_authority": "QuickBooks Online financial snapshot",
            "missing_config": [],
            "last_updated": None,
            "accounts_payable": {
                "pending_amount": 100,
                "pending_bills": 1,
                "overdue_amount": 0,
                "overdue_count": 0,
                "total": 100,
            },
            "accounts_receivable": [{"bucket": "0-30", "amount": 200, "count": 1}],
            "cash_flow": {"bank_balance": None, "net_weekly": None, "weekly_income": None, "weekly_expenses": None, "k1l_expense_total": 75},
        },
    )
    monkeypatch.setattr(
        control_tower_service,
        "_fetch_xcelerator_event_rows",
        lambda: (
            [
                {
                    "driver_pay_amount": 850,
                    "event_type": "shipment_financial_update",
                    "revenue_amount": 2400,
                    "shipment_id": "SH-1001",
                    "timestamp": "2026-05-16T12:35:00Z",
                }
            ],
            datetime(2026, 5, 16, 12, 35, tzinfo=timezone.utc),
        ),
    )

    response = _client().get("/api/control-tower/financial")

    assert response.status_code == 200
    payload = response.json()
    assert payload["accounts_payable"]["pending_amount"] == 100
    assert payload["feeds"][0]["status"] == "healthy"
    assert payload["feeds"][1]["status"] == "healthy"
    assert "Read 1 Xcelerator row" in payload["feeds"][0]["message"]
    assert "adapter is not live yet" not in payload["feeds"][0]["message"]
    assert "12345" not in response.text


def test_financial_uses_review_orders_evidence_when_event_url_is_not_row_feed(monkeypatch, tmp_path):
    evidence_path = tmp_path / "review-orders.json"
    evidence_path.write_text('{"rows":[{"Order ID":"1.020126","Driver Pay":280}]}', encoding="utf-8")
    monkeypatch.setenv("FLEETPULSE_FINANCIAL_FEED_ENABLED", "true")
    monkeypatch.setenv("FLEETPULSE_XCELERATOR_EVENT_FEED_URL", "https://example.invalid/xcelerator")
    monkeypatch.setenv("FLEETPULSE_XCELERATOR_REVIEW_ORDERS_STATE_PATH", str(evidence_path))
    monkeypatch.setattr(
        control_tower_service,
        "_fetch_xcelerator_event_rows",
        lambda: (_ for _ in ()).throw(RuntimeError("not_a_row_feed")),
    )

    response = _client().get("/api/control-tower/financial")

    assert response.status_code == 200
    payload = response.json()
    xcelerator_feed = payload["feeds"][0]
    assert xcelerator_feed["status"] == "healthy"
    assert "ReviewOrders evidence file is available" in xcelerator_feed["message"]
    assert "using persisted Xcelerator evidence" in xcelerator_feed["message"]
    assert "FLEETPULSE_XCELERATOR_REVIEW_ORDERS_STATE_PATH" in xcelerator_feed["required_config"]


def test_trailer_mailbox_config_reports_adapter_pending(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_XTRA_INGESTION_ENABLED", "false")
    monkeypatch.setenv("FLEETPULSE_XTRA_OUTLOOK_MAILBOX", "rami@example.com")
    monkeypatch.setenv("FLEETPULSE_XTRA_GEOFENCE_FOLDER", "XTRA Lease Trailer Geofence Tracker")
    monkeypatch.setattr(
        control_tower_service,
        "GeotabClient",
        type(
            "FakeGeotabClient",
            (),
            {"get": staticmethod(lambda: type("Client", (), {"get_devices": lambda self: [], "get_device_status_info": lambda self: []})())},
        ),
    )

    response = _client().get("/api/control-tower/trailers")

    assert response.status_code == 200
    payload = response.json()
    xtra_feed = next(feed for feed in payload["feeds"] if feed["name"] == "XTRA Outlook geofence feed")
    assert xtra_feed["status"] == "warning"
    assert "ingestion is not enabled yet" in xtra_feed["message"]


def test_xtra_ingest_endpoint_requires_api_key(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_XTRA_INGESTION_API_KEY", "expected")

    response = _client().post("/api/control-tower/trailers/xtra/ingest")

    assert response.status_code == 401


def test_xtra_ingest_endpoint_runs_with_valid_api_key(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_XTRA_INGESTION_API_KEY", "expected")

    class FakeResult:
        def as_dict(self):
            return {"status": "ok", "imported_count": 1}

    monkeypatch.setattr(control_tower, "ingest_xtra_lease_emails", lambda config: FakeResult())

    response = _client().post(
        "/api/control-tower/trailers/xtra/ingest",
        headers={"X-FleetPulse-Xtra-Key": "expected"},
    )

    assert response.status_code == 200
    assert response.json()["imported_count"] == 1


def test_live_trailer_tracking_endpoint_returns_projection(monkeypatch):
    monkeypatch.setattr(
        control_tower,
        "get_live_trailer_tracking",
        lambda: ControlTowerTrailerTrackingResponse(generated_at=datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc)),
    )

    response = _client().get("/api/control-tower/trailers/live")

    assert response.status_code == 200
    assert response.json()["projection_mode"] == "read_only"


def test_agents_report_configuration_presence_without_secret_values(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-value")
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4")
    monkeypatch.setattr(control_tower_service, "get_monitor_status", lambda: {"running": True})

    response = _client().get("/api/control-tower/agents")

    assert response.status_code == 200
    payload = response.json()
    openrouter = next(system for system in payload["systems"] if system["name"] == "OpenRouter AI")
    assert openrouter["status"] == "healthy"
    assert "secret-value" not in response.text


def test_codex_uses_runtime_metadata_when_present(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "K1-Group/k1-fleetpulse")
    monkeypatch.setenv("GITHUB_SHA", "abcdef1234567890")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")

    response = _client().get("/api/control-tower/codex")

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] == "healthy"
    assert payload["repository"] == "K1-Group/k1-fleetpulse"
    assert payload["commit_sha"] == "abcdef123456"


def test_overview_lists_all_restored_sections(monkeypatch):
    monkeypatch.setattr(control_tower_service, "get_recent_alerts", lambda hours=24: [])
    monkeypatch.setattr(control_tower_service, "get_monitor_alerts", lambda limit=50: [])
    monkeypatch.setattr(control_tower_service, "get_monitor_status", lambda: {"running": False})

    response = _client().get("/api/control-tower/overview")

    assert response.status_code == 200
    keys = {section["key"] for section in response.json()["sections"]}
    assert keys == {"attention", "trailers", "financial", "agents", "codex"}
