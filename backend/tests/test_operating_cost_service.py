"""Tests for source-backed operating cost rollups."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services import operating_cost_service as service  # noqa: E402
from services.atob_fuel_expense_service import (  # noqa: E402
    AtoBFuelExpenseStateStore,
    import_atob_fuel_expenses,
)
from services.lane_stability_service import LaneStabilityConfig  # noqa: E402
from services.qbo_expense_import_service import QboExpenseStateStore, import_qbo_expenses  # noqa: E402
from integrations.xcelerator.review_orders_feed import ReviewOrdersFeedConfig  # noqa: E402


def test_operating_cost_snapshot_joins_true_source_components(monkeypatch, tmp_path):
    atob_store = AtoBFuelExpenseStateStore(path=tmp_path / "atob.json")
    import_atob_fuel_expenses(
        "\n".join(
            [
                "Transaction ID,Transaction Date,Status,Amount,Net of Discount,Gallons,Type,Vehicle",
                "A-1,2026-05-04,Approved,110.00,100.00,20.0,Diesel,Truck 1",
                "A-2,2026-05-05,Declined,999.00,999.00,99.0,Diesel,Truck 1",
            ]
        ),
        filename="atob.csv",
        store=atob_store,
    )

    async def fake_vehicle_kpis(start, end):
        return [
            {
                "Local_Date": start.isoformat(),
                "Distance_Km": 160.934,
                "TotalDriveTime_Hours": 5,
                "TotalIdleTime_Hours": 1,
                "TotalTrips": 4,
            }
        ]

    monkeypatch.setattr(service, "_fetch_vehicle_kpi_rows", fake_vehicle_kpis)

    lane_path = tmp_path / "review-orders.csv"
    lane_path.write_text(
        "\n".join(
            [
                "[P]From Date,Service,Ref#,DriverNo,RouteNo,Grand Total,Gross Margin($),Driver Pay",
                "05/04/2026,LH,HDS K1,D1,R1,1000,700,250",
                "05/10/2026,LH,HDS K1,D1,R1,10,10,0",
            ]
        ),
        encoding="utf-8",
    )
    lane_config = LaneStabilityConfig(
        order_feed=ReviewOrdersFeedConfig(path=str(lane_path)),
        baseline_feed=ReviewOrdersFeedConfig(),
        excluded_scoring_services=(),
        excluded_scoring_ref_patterns=(),
    )

    qbo_path = tmp_path / "qbo-expenses.csv"
    qbo_path.write_text(
        "\n".join(
            [
                "Date,Account,Amount",
                "2026-05-04,Commercial Auto Insurance,50.00",
                "2026-05-05,Repairs and Maintenance,75.00",
                "2026-05-05,Carrier & Factoring Company,900.00",
                "2026-05-05,Contractors,100.00",
                "2026-05-05,Fuel Expense,999.00",
            ]
        ),
        encoding="utf-8",
    )
    qbo_config = service.QboExpenseFeedConfig(path=str(qbo_path))

    snapshot = asyncio.run(
        service.get_operating_cost_snapshot(
            start="2026-05-04",
            end="2026-05-10",
            atob_store=atob_store,
            lane_config=lane_config,
            qbo_config=qbo_config,
        )
    )

    assert snapshot["complete_cost_available"] is True
    assert snapshot["summary"]["fuel_cost"] == 100.0
    assert snapshot["summary"]["driver_pay"] == 250.0
    assert snapshot["summary"]["insurance_cost"] == 50.0
    assert snapshot["summary"]["other_expense_cost"] == 75.0
    assert snapshot["summary"]["true_operating_cost"] == 475.0
    assert snapshot["summary"]["true_cost_per_mile"] == 4.75
    assert snapshot["summary"]["true_cost_per_drive_hour"] == 95.0


def test_operating_cost_snapshot_marks_missing_qbo_as_incomplete(monkeypatch, tmp_path):
    async def fake_vehicle_kpis(start, end):
        return [
            {
                "Distance_Km": 160.934,
                "TotalDriveTime_Hours": 5,
                "TotalIdleTime_Hours": 0,
            }
        ]

    monkeypatch.setattr(service, "_fetch_vehicle_kpi_rows", fake_vehicle_kpis)
    lane_config = LaneStabilityConfig(
        order_feed=ReviewOrdersFeedConfig(),
        baseline_feed=ReviewOrdersFeedConfig(),
        excluded_scoring_services=(),
        excluded_scoring_ref_patterns=(),
    )
    snapshot = asyncio.run(
        service.get_operating_cost_snapshot(
            start="2026-05-04",
            end="2026-05-10",
            atob_store=AtoBFuelExpenseStateStore(path=tmp_path / "missing-atob.json"),
            lane_config=lane_config,
            qbo_config=service.QboExpenseFeedConfig(),
        )
    )

    assert snapshot["complete_cost_available"] is False
    assert "fuel" in snapshot["unresolved_sources"]
    assert "driver_pay" in snapshot["unresolved_sources"]
    assert "qbo_expenses" in snapshot["unresolved_sources"]
    assert snapshot["summary"]["true_cost_per_mile"] is None


def test_operating_cost_snapshot_marks_configured_empty_qbo_as_incomplete(monkeypatch, tmp_path):
    async def fake_vehicle_kpis(start, end):
        return [
            {
                "Distance_Km": 160.934,
                "TotalDriveTime_Hours": 5,
                "TotalIdleTime_Hours": 0,
            }
        ]

    monkeypatch.setattr(service, "_fetch_vehicle_kpi_rows", fake_vehicle_kpis)
    lane_config = LaneStabilityConfig(
        order_feed=ReviewOrdersFeedConfig(),
        baseline_feed=ReviewOrdersFeedConfig(),
        excluded_scoring_services=(),
        excluded_scoring_ref_patterns=(),
    )

    snapshot = asyncio.run(
        service.get_operating_cost_snapshot(
            start="2026-05-04",
            end="2026-05-10",
            atob_store=AtoBFuelExpenseStateStore(path=tmp_path / "missing-atob.json"),
            lane_config=lane_config,
            qbo_config=service.QboExpenseFeedConfig(path=str(tmp_path / "missing-qbo.json")),
        )
    )

    assert snapshot["complete_cost_available"] is False
    assert snapshot["sources"]["qbo_expenses"]["status"] == "awaiting_feed"
    assert "no expense rows" in snapshot["sources"]["qbo_expenses"]["message"].lower()


def test_operating_cost_snapshot_marks_partial_driver_pay_as_incomplete(monkeypatch, tmp_path):
    async def fake_vehicle_kpis(start, end):
        return [
            {
                "Distance_Km": 160.934,
                "TotalDriveTime_Hours": 5,
                "TotalIdleTime_Hours": 0,
            }
        ]

    monkeypatch.setattr(service, "_fetch_vehicle_kpi_rows", fake_vehicle_kpis)
    atob_store = AtoBFuelExpenseStateStore(path=tmp_path / "atob.json")
    import_atob_fuel_expenses(
        "Transaction ID,Transaction Date,Status,Amount,Net of Discount,Gallons,Type,Vehicle\n"
        "A-1,2026-05-04,Approved,110.00,100.00,20.0,Diesel,Truck 1\n",
        filename="atob.csv",
        store=atob_store,
    )
    lane_path = tmp_path / "review-orders.csv"
    lane_path.write_text(
        "\n".join(
            [
                "[P]From Date,Service,Ref#,DriverNo,RouteNo,Grand Total,Gross Margin($),Driver Pay",
                "05/04/2026,LH,HDS K1,D1,R1,1000,700,250",
            ]
        ),
        encoding="utf-8",
    )
    lane_config = LaneStabilityConfig(
        order_feed=ReviewOrdersFeedConfig(path=str(lane_path)),
        baseline_feed=ReviewOrdersFeedConfig(),
        excluded_scoring_services=(),
        excluded_scoring_ref_patterns=(),
    )
    qbo_path = tmp_path / "qbo-expenses.csv"
    qbo_path.write_text("Date,Account,Amount\n2026-05-04,Insurance,50.00\n", encoding="utf-8")

    snapshot = asyncio.run(
        service.get_operating_cost_snapshot(
            start="2026-05-04",
            end="2026-05-10",
            atob_store=atob_store,
            lane_config=lane_config,
            qbo_config=service.QboExpenseFeedConfig(path=str(qbo_path)),
        )
    )

    assert snapshot["complete_cost_available"] is False
    assert snapshot["sources"]["driver_pay"]["status"] == "partial"
    assert "driver_pay" in snapshot["unresolved_sources"]
    assert snapshot["summary"]["known_operating_cost"] == 400.0
    assert snapshot["summary"]["true_cost_per_mile"] is None


def test_operating_cost_snapshot_reads_imported_qbo_expense_state(monkeypatch, tmp_path):
    atob_store = AtoBFuelExpenseStateStore(path=tmp_path / "atob.json")
    import_atob_fuel_expenses(
        "Transaction ID,Transaction Date,Status,Amount,Gallons,Type,Vehicle\n"
        "A-1,2026-05-04,Approved,100.00,20.0,Diesel,Truck 1\n",
        filename="atob.csv",
        store=atob_store,
    )

    async def fake_vehicle_kpis(start, end):
        return [
            {
                "Distance_Km": 160.934,
                "TotalDriveTime_Hours": 5,
                "TotalIdleTime_Hours": 1,
            }
        ]

    monkeypatch.setattr(service, "_fetch_vehicle_kpi_rows", fake_vehicle_kpis)

    lane_path = tmp_path / "review-orders.csv"
    lane_path.write_text(
        "\n".join(
            [
                "PFrom Date,Order ID,Driver Pay",
                "05/04/2026,1.050426,250",
            ]
        ),
        encoding="utf-8",
    )
    lane_config = LaneStabilityConfig(
        order_feed=ReviewOrdersFeedConfig(path=str(lane_path)),
        baseline_feed=ReviewOrdersFeedConfig(),
        excluded_scoring_services=(),
        excluded_scoring_ref_patterns=(),
    )

    qbo_store = QboExpenseStateStore(path=tmp_path / "qbo-expenses.json")
    import_qbo_expenses(
        "\n".join(
            [
                "Date,Name,Account,Amount",
                "05/04/2026,Insurance Co,Insurance,50",
                "05/05/2026,Repair Shop,Repairs and Maintenance,75",
                "05/05/2026,AtoB,Fuel Expense,999",
            ]
        ),
        filename="qbo.csv",
        period_start="2026-05-04",
        period_end="2026-05-10",
        store=qbo_store,
    )

    snapshot = asyncio.run(
        service.get_operating_cost_snapshot(
            start="2026-05-04",
            end="2026-05-10",
            atob_store=atob_store,
            lane_config=lane_config,
            qbo_config=service.QboExpenseFeedConfig(path=str(qbo_store.path)),
        )
    )

    assert snapshot["sources"]["qbo_expenses"]["status"] == "healthy"
    assert snapshot["sources"]["qbo_expenses"]["row_count"] == 3
    assert snapshot["summary"]["insurance_cost"] == 50.0
    assert snapshot["summary"]["other_expense_cost"] == 75.0
    assert snapshot["summary"]["known_operating_cost"] == 225.0
