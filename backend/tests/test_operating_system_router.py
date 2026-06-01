"""Tests for the K1 seat-based operating system portal contract."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from routers import operating_system  # noqa: E402


@pytest.fixture(autouse=True)
def clear_operating_system_api_key(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_OPERATING_SYSTEM_REQUIRE_API_KEY", "false")
    monkeypatch.delenv("FLEETPULSE_OPERATING_SYSTEM_API_KEY", raising=False)
    monkeypatch.delenv("OPERATING_SYSTEM_API_KEY", raising=False)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(operating_system.router, prefix="/api/operating-system")
    return TestClient(app)


def test_org_chart_exposes_fixed_seat_contract_and_boundaries():
    response = _client().get("/api/operating-system/org-chart")

    assert response.status_code == 200
    payload = response.json()
    assert payload["projection_mode"] == "read_only"
    assert payload["source_document"]["name"] == "k1-seat-based-org-chart.pptx"
    assert payload["targets"]["annual_target"] == 30_000_000
    assert payload["total_seats"] == 24
    assert payload["accountability_seats"] == 6
    assert payload["functional_seats"] == 18
    systems = {boundary["system"] for boundary in payload["source_boundaries"]}
    assert {"Xcelerator", "Geotab", "QuickBooks", "Time Doctor", "Power BI"} <= systems
    assert "GET /api/operating-system/seats/{seat_id}" in payload["endpoint_contract"]


def test_management_tree_assigns_revenue_and_operations_seats():
    response = _client().get("/api/operating-system/org-chart")

    assert response.status_code == 200
    tree = {node["manager_seat_id"]: node for node in response.json()["management_tree"]}
    assert tree["revenue_manager"]["functional_seat_ids"] == [
        "lead_generation",
        "sales_development",
        "account_executive",
        "account_manager",
        "pricing_margin",
    ]
    assert "dispatch" in tree["operations_manager"]["functional_seat_ids"]


def test_task_kpi_matrix_returns_scorecard_weights_and_no_live_actuals():
    response = _client().get("/api/operating-system/task-kpi-matrix")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scorecard_weights"] == {"kpi": 70, "queue_sla": 20, "work_evidence": 10}
    assert len(payload["seats"]) == 24
    dispatch = next(seat for seat in payload["seats"] if seat["seat_id"] == "dispatch")
    assert dispatch["manager_seat_id"] == "operations_manager"
    assert dispatch["targets"]["loads_dispatched_day"] == ">= 8"
    assert "actual" not in response.text.lower()


def test_seat_detail_preserves_source_authority_split():
    response = _client().get("/api/operating-system/seats/fleet_maintenance")

    assert response.status_code == 200
    payload = response.json()
    assert payload["seat"]["entity_scope"] == "K1 Logistics Inc"
    assert payload["seat"]["source_authorities"] == ["Geotab", "SharePoint"]
    geotab = next(boundary for boundary in payload["source_boundaries"] if boundary["system"] == "Geotab")
    assert geotab["entity"] == "K1 Logistics Inc"
    assert "telemetry" in geotab["authority"]


def test_task_kpi_matrix_for_unknown_seat_returns_404():
    response = _client().get("/api/operating-system/task-kpi-matrix/not_a_seat")

    assert response.status_code == 404
    assert response.json()["detail"] == "seat_not_found"


def test_configuration_endpoint_reports_env_status_without_values(monkeypatch):
    monkeypatch.setenv("XCELERATOR_API_BASE_URL", "https://xcelerator.example")
    monkeypatch.setenv("SHAREPOINT_SITE_ID", "site-id-value")

    response = _client().get("/api/operating-system/configuration")

    assert response.status_code == 200
    payload = response.json()
    assert payload["projection_mode"] == "read_only"
    assert payload["api_key_required"] is False
    status_by_env = {item["env_var"]: item for item in payload["items"]}
    assert status_by_env["XCELERATOR_API_BASE_URL"]["configured"] is True
    assert status_by_env["SHAREPOINT_SITE_ID"]["configured"] is True
    assert "https://xcelerator.example" not in response.text
    assert "site-id-value" not in response.text


def test_operating_system_api_key_is_required_when_configured(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_OPERATING_SYSTEM_API_KEY", "expected")

    missing = _client().get("/api/operating-system/org-chart")
    valid = _client().get(
        "/api/operating-system/org-chart",
        headers={"X-FleetPulse-Operating-System-Key": "expected"},
    )
    fallback_header = _client().get(
        "/api/operating-system/task-kpi-matrix",
        headers={"X-API-Key": "expected"},
    )

    assert missing.status_code == 401
    assert missing.json()["detail"] == "invalid_operating_system_api_key"
    assert valid.status_code == 200
    assert fallback_header.status_code == 200


def test_operating_system_api_key_requirement_fails_closed_without_key(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_OPERATING_SYSTEM_REQUIRE_API_KEY", "true")

    response = _client().get("/api/operating-system/configuration")

    assert response.status_code == 503
    assert response.json()["detail"] == "operating_system_api_key_not_configured"


def test_configuration_reports_api_key_required_when_enabled(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_OPERATING_SYSTEM_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("FLEETPULSE_OPERATING_SYSTEM_API_KEY", "expected")

    response = _client().get(
        "/api/operating-system/configuration",
        headers={"X-FleetPulse-Operating-System-Key": "expected"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_key_required"] is True
    status_by_env = {item["env_var"]: item for item in payload["items"]}
    assert status_by_env["FLEETPULSE_OPERATING_SYSTEM_REQUIRE_API_KEY"]["configured"] is True
    assert status_by_env["FLEETPULSE_OPERATING_SYSTEM_API_KEY"]["configured"] is True
    assert "expected" not in response.text
