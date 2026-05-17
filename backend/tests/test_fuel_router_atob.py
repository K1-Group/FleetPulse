"""Tests for Fuel Analytics AtoB import router."""

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

from _cache import clear_cached_prefix  # noqa: E402
from routers import fuel  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(fuel.router, prefix="/api/fuel")
    return TestClient(app)


def _sample_csv(transaction_id: str = "A-100") -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    return (
        "Transaction ID,Transaction Date,Merchant,Amount,Gallons,Vehicle\n"
        f"{transaction_id},{today},Pilot,250.00,50.0,5439 Idealease -HDS DFW\n"
    )


def _sample_atob_export_csv() -> str:
    return "\n".join(
        [
            (
                "Transaction Date (GMT),Posted Date (GMT),Status,Card Last Four,"
                "Merchant,Amount,Net of Discount,Discount,Driver Name,Vehicle Name,"
                "Merchant Category,Type,Gallons,Price Per Gallon,UUID"
            ),
            (
                "05/14/2026 15:15:53,05/14/2026 16:11:20,Approved,**** 6763,"
                "PILOT_00507,$495.00,$490.48,$4.52,Taleise Oliver,Truck 1,"
                "automated_fuel_dispensers,Diesel,90.345,$5.479,txn-1"
            ),
            (
                "05/14/2026 15:19:14,,Pending,**** 4913,Love's #0269 C Outside,"
                "$904.99,,,Roddrick Blow,Truck 2,automated_fuel_dispensers,,,"
                ",txn-2"
            ),
        ]
    )


def test_atob_import_endpoint_summarizes_actual_expenses(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEETPULSE_ATOB_FUEL_STATE_PATH", str(tmp_path / "atob-state.json"))
    clear_cached_prefix("fuel:")

    response = _client().post(
        "/api/fuel/atob/import",
        json={
            "filename": "atob.csv",
            "content": _sample_csv(),
            "dry_run": False,
        },
    )
    summary = _client().get("/api/fuel/atob/summary?days=30")

    assert response.status_code == 200
    assert response.json()["imported_count"] == 1
    assert summary.status_code == 200
    assert summary.json()["transaction_count"] == 1
    assert summary.json()["total_cost"] == 250.0


def test_atob_import_endpoint_accepts_generic_export_headers(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEETPULSE_ATOB_FUEL_STATE_PATH", str(tmp_path / "atob-state.json"))
    clear_cached_prefix("fuel:")

    response = _client().post(
        "/api/fuel/atob/import",
        json={
            "filename": "K1_Logistics_Inc_Transactions_generic_Export_2026-05-14.csv",
            "content": _sample_atob_export_csv(),
            "dry_run": False,
        },
    )
    summary = _client().get("/api/fuel/atob/summary?days=30")

    assert response.status_code == 200
    assert response.json()["imported_count"] == 2
    assert response.json()["summary"]["transaction_count"] == 1
    assert summary.status_code == 200
    assert summary.json()["transaction_count"] == 1
    assert summary.json()["total_cost"] == 490.48


def test_fuel_summary_prefers_atob_actual_cost_when_imported(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEETPULSE_ATOB_FUEL_STATE_PATH", str(tmp_path / "atob-state.json"))
    clear_cached_prefix("fuel:")

    class FakeGeotabClient:
        def get_trips(self, from_date=None, to_date=None):
            return [
                {
                    "start": datetime.now(timezone.utc).isoformat(),
                    "distance": 160.934,
                    "device": {"id": "device-1"},
                }
            ]

        def get_exception_events(self, from_date=None, to_date=None):
            return []

        def get_devices(self):
            return [{"id": "device-1", "name": "5439 Idealease -HDS DFW"}]

    monkeypatch.setattr(fuel.GeotabClient, "get", staticmethod(lambda: FakeGeotabClient()))

    client = _client()
    client.post(
        "/api/fuel/atob/import",
        json={
            "filename": "atob.csv",
            "content": _sample_csv("A-200"),
            "dry_run": False,
        },
    )
    response = client.get("/api/fuel/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["fuel_cost_source"] == "atob_manual_import"
    assert payload["period_30d"]["total_cost"] == 250.0
    assert payload["period_30d"]["actual_fuel_cost"] is True


def test_atob_sharepoint_sync_endpoint_requires_key(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_ATOB_SHAREPOINT_INGESTION_API_KEY", "expected")

    response = _client().post("/api/fuel/atob/sharepoint/sync", json={"dry_run": True})

    assert response.status_code == 401


def test_atob_sharepoint_sync_endpoint_runs_with_valid_key(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_ATOB_SHAREPOINT_INGESTION_API_KEY", "expected")

    class FakeResult:
        dry_run = False
        imported_count = 1

        def as_dict(self):
            return {
                "status": "ok",
                "source_authority": "SharePoint / AtoB fuel folder",
                "imported_count": 1,
            }

    monkeypatch.setattr(fuel, "sync_atob_sharepoint_folder", lambda config, dry_run=False: FakeResult())

    response = _client().post(
        "/api/fuel/atob/sharepoint/sync",
        json={"dry_run": False},
        headers={"X-FleetPulse-AtoB-Key": "expected"},
    )

    assert response.status_code == 200
    assert response.json()["imported_count"] == 1


def test_atob_sharepoint_status_does_not_expose_secret(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_ATOB_SHAREPOINT_ENABLED", "true")
    monkeypatch.setenv("FLEETPULSE_ATOB_SHAREPOINT_INGESTION_API_KEY", "expected")

    response = _client().get("/api/fuel/atob/sharepoint/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_key_required"] is True
    assert "expected" not in response.text


def test_operating_cost_endpoint_returns_weekly_snapshot(monkeypatch):
    async def fake_snapshot(days=90, start=None, end=None):
        return {
            "period_start": start,
            "period_end": end or "2026-05-14",
            "projection_mode": "read_only",
            "complete_cost_available": False,
            "summary": {"known_cost_per_mile": 0.62},
            "weekly": [],
        }

    monkeypatch.setattr(fuel, "get_operating_cost_snapshot", fake_snapshot)

    response = _client().get("/api/fuel/operating-cost?start=2026-01-01&end=2026-05-14")

    assert response.status_code == 200
    assert response.json()["summary"]["known_cost_per_mile"] == 0.62


def test_entity_margin_endpoint_returns_k1_entity_snapshot(monkeypatch):
    async def fake_snapshot(days=90, start=None, end=None):
        return {
            "period_start": start,
            "period_end": end or "2026-05-14",
            "projection_mode": "read_only",
            "complete_k1l_cpm_available": True,
            "summary": {
                "k1l_fuel_plus_driver_cpm": 1.63,
                "k1g_target_gross_margin": 194283.57,
            },
            "weekly": [],
        }

    monkeypatch.setattr(fuel, "get_entity_margin_snapshot", fake_snapshot)

    response = _client().get("/api/fuel/entity-margin?start=2026-01-01&end=2026-05-14")

    assert response.status_code == 200
    assert response.json()["summary"]["k1l_fuel_plus_driver_cpm"] == 1.63
    assert response.json()["summary"]["k1g_target_gross_margin"] == 194283.57


def test_k1l_operating_kpi_endpoint_returns_configured_final_cpm(monkeypatch):
    monkeypatch.setenv(
        "K1L_OPERATING_COST_MONTHLY_JSON",
        """
        {
          "asOfDate": "2026-05-14",
          "months": [
            {
              "month": "2026-01",
              "miles": 314555.8,
              "driverPay": 346108.5,
              "fuel": 151524.27,
              "fleetMaintenance": 55734.77,
              "payroll": 89232.46,
              "otherOps": 101258.57,
              "revenue": 1200000
            }
          ]
        }
        """,
    )

    response = _client().get("/api/fuel/k1l-operating-kpi?date=2026-05-14")

    assert response.status_code == 200
    payload = response.json()
    assert payload["projection_mode"] == "read_only"
    assert payload["status"] == "configured"
    assert payload["entity"] == "K1 Logistics Inc"
    assert payload["summary"]["total_cost"] == 743858.57
    assert payload["summary"]["cost_per_mile"] == 2.365
    assert payload["summary"]["revenue"] == 1200000.0
    assert payload["summary"]["revenue_per_mile"] == 3.815
    assert payload["summary"]["profit_per_mile"] == 1.45
    assert payload["monthly"][0]["gross_profit"] == 456141.43
    assert payload["monthly"][0]["added_p_and_l_ops"] == 190491.03


def test_xcelerator_review_orders_import_endpoint_summarizes_driver_pay(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "FLEETPULSE_XCELERATOR_REVIEW_ORDERS_STATE_PATH",
        str(tmp_path / "review-orders.json"),
    )
    clear_cached_prefix("fuel:")

    csv_content = "\n".join(
        [
            "Route No,Driver No,Company Name,Order ID,PFrom Date,Grand Total,Order Charge,Driver Pay",
            "--- FEB 1 (SUNDAY) --,,,,,,,",
            "DFW 004,4,K1 Logistics Inc,1.020126,02/01/2026,0,0,280",
            "DFW 005,155,K1 Logistics Inc,3.020126,02/01/2026,0,0,320",
        ]
    )

    response = _client().post(
        "/api/fuel/xcelerator/review-orders/import",
        json={
            "filename": "review-orders.csv",
            "content": csv_content,
            "dry_run": False,
        },
    )
    summary = _client().get("/api/fuel/xcelerator/review-orders/summary?days=370")

    assert response.status_code == 200
    assert response.json()["imported_count"] == 2
    assert response.json()["summary"]["driver_pay_total"] == 600.0
    assert summary.status_code == 200
    assert summary.json()["driver_pay_total"] == 600.0


def test_qbo_expense_import_endpoint_summarizes_operating_expenses(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEETPULSE_QBO_EXPENSE_STATE_PATH", str(tmp_path / "qbo-expenses.json"))
    clear_cached_prefix("fuel:")

    csv_content = "\n".join(
        [
            "Date,Transaction Type,Name,Account,Amount",
            "01/05/2026,Expense,Insurance Co,Commercial Auto Insurance,500",
            "01/06/2026,Expense,Repair Shop,Repairs and Maintenance,125.25",
            "01/07/2026,Expense,AtoB,Fuel Expense,999",
        ]
    )

    response = _client().post(
        "/api/fuel/qbo/expenses/import",
        json={
            "filename": "qbo-expenses.csv",
            "content": csv_content,
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "dry_run": False,
        },
    )
    summary = _client().get("/api/fuel/qbo/expenses/summary?days=370")

    assert response.status_code == 200
    assert response.json()["imported_count"] == 3
    assert response.json()["summary"]["insurance_total"] == 500.0
    assert response.json()["summary"]["other_expense_total"] == 125.25
    assert response.json()["summary"]["excluded_expense_count"] == 1
    assert summary.status_code == 200
    assert summary.json()["coverage_start"] == "2026-01-01"
    assert summary.json()["coverage_end"] == "2026-01-31"


def test_qbo_expense_import_endpoint_honors_optional_key(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEETPULSE_QBO_EXPENSE_STATE_PATH", str(tmp_path / "qbo-expenses.json"))
    monkeypatch.setenv("FLEETPULSE_QBO_EXPENSE_IMPORT_API_KEY", "expected")

    response = _client().post(
        "/api/fuel/qbo/expenses/import",
        json={
            "filename": "qbo-expenses.csv",
            "content": "Date,Account,Amount\n01/05/2026,Insurance,500\n",
            "dry_run": False,
        },
    )
    authorized = _client().post(
        "/api/fuel/qbo/expenses/import",
        json={
            "filename": "qbo-expenses.csv",
            "content": "Date,Account,Amount\n01/05/2026,Insurance,500\n",
            "dry_run": False,
        },
        headers={"X-FleetPulse-QBO-Key": "expected"},
    )

    assert response.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["imported_count"] == 1
