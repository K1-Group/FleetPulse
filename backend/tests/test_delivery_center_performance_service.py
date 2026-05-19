"""Tests for delivery-center pickup/delivery on-time performance."""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services import delivery_center_performance_service as service  # noqa: E402


def test_delivery_center_performance_groups_pickup_and_delivery_by_center():
    rows = [
        {
            "order_date": date(2026, 5, 1),
            "delivery_center": "K1 Logistics Inc",
            "pickup_due_at": datetime(2026, 5, 1, 8),
            "pickup_actual_at": datetime(2026, 5, 1, 8, 10),
            "delivery_due_at": datetime(2026, 5, 1, 18),
            "delivery_actual_at": datetime(2026, 5, 1, 17, 55),
        },
        {
            "order_date": date(2026, 5, 2),
            "delivery_center": "K1 Logistics Inc",
            "pickup_due_at": datetime(2026, 5, 2, 8),
            "pickup_actual_at": datetime(2026, 5, 2, 8, 35),
            "delivery_due_at": datetime(2026, 5, 2, 18),
            "delivery_actual_at": datetime(2026, 5, 2, 18, 40),
        },
        {
            "order_date": date(2026, 5, 3),
            "delivery_center": "K1 Group LLC",
            "pickup_due_at": datetime(2026, 5, 3, 8),
            "pickup_actual_at": datetime(2026, 5, 3, 8, 5),
            "delivery_due_at": datetime(2026, 5, 3, 18),
            "delivery_actual_at": datetime(2026, 5, 3, 18, 5),
        },
    ]

    centers, summary = service._delivery_center_performance_from_rows(
        rows,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 7),
        tolerance_minutes=15,
    )

    k1l = next(row for row in centers if row["delivery_center"] == "K1 Logistics Inc")
    assert k1l["orders"] == 2
    assert k1l["pickup_measured_orders"] == 2
    assert k1l["pickup_on_time_orders"] == 1
    assert k1l["pickup_late_orders"] == 1
    assert k1l["pickup_on_time_pct"] == 0.5
    assert k1l["pickup_avg_late_minutes"] == 20
    assert k1l["delivery_on_time_orders"] == 1
    assert k1l["delivery_late_orders"] == 1
    assert k1l["delivery_on_time_pct"] == 0.5
    assert k1l["delivery_avg_late_minutes"] == 25
    assert summary["orders"] == 3
    assert summary["pickup_on_time_pct"] == 0.6667
    assert summary["delivery_on_time_pct"] == 0.6667


def test_delivery_center_performance_tracks_missing_proof():
    rows = [
        {
            "order_date": date(2026, 5, 1),
            "delivery_center": "K1 Logistics Inc",
            "pickup_due_at": datetime(2026, 5, 1, 8),
            "pickup_actual_at": None,
            "delivery_due_at": None,
            "delivery_actual_at": datetime(2026, 5, 1, 18),
        },
        {
            "order_date": date(2026, 5, 2),
            "delivery_center": "K1 Logistics Inc",
            "pickup_due_at": datetime(2026, 5, 2, 8),
            "pickup_actual_at": datetime(2026, 5, 2, 7, 45),
            "delivery_due_at": datetime(2026, 5, 2, 18),
            "delivery_actual_at": None,
        },
    ]

    centers, summary = service._delivery_center_performance_from_rows(
        rows,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 7),
    )

    k1l = centers[0]
    assert k1l["pickup_measured_orders"] == 1
    assert k1l["pickup_missing_orders"] == 1
    assert k1l["pickup_missing_actual_orders"] == 1
    assert k1l["pickup_proof_coverage_pct"] == 0.5
    assert k1l["delivery_measured_orders"] == 0
    assert k1l["delivery_missing_orders"] == 2
    assert k1l["delivery_missing_schedule_orders"] == 1
    assert k1l["delivery_missing_actual_orders"] == 1
    assert k1l["delivery_on_time_pct"] is None
    assert summary["pickup_proof_coverage_pct"] == 0.5
    assert summary["delivery_proof_coverage_pct"] == 0


def test_delivery_center_performance_snapshot_uses_revieworders_columns(monkeypatch):
    monkeypatch.setattr(service.FabricWarehouseSqlConfig, "from_env", lambda prefix: SimpleNamespace(configured=True))

    def fake_sql(config, query):
        if "GROUP BY schemas.name" in query:
            return [{"table_schema": "dbo", "table_name": "xcelerator_review_orders"}]
        if "columns.name AS column_name" in query:
            return [
                {"column_name": "[P]From Date"},
                {"column_name": "Delivery Center"},
                {"column_name": "[P]To"},
                {"column_name": "[P]Arrival"},
                {"column_name": "[D]To"},
                {"column_name": "[D]Arrival"},
            ]
        assert "[dbo].[xcelerator_review_orders]" in query
        assert "TRY_CONVERT(datetime2, [[P]]To]) AS pickup_due_at" in query
        assert "TRY_CONVERT(datetime2, [[D]]Arrival]) AS delivery_actual_at" in query
        return [
            {
                "order_date": date(2026, 5, 1),
                "delivery_center": "K1 Logistics Inc",
                "pickup_due_at": datetime(2026, 5, 1, 8),
                "pickup_actual_at": datetime(2026, 5, 1, 8),
                "delivery_due_at": datetime(2026, 5, 1, 18),
                "delivery_actual_at": datetime(2026, 5, 1, 18, 30),
            }
        ]

    monkeypatch.setattr(service, "execute_sql_query", fake_sql)

    snapshot = service.get_delivery_center_performance_snapshot(
        start="2026-05-01",
        end="2026-05-07",
        tolerance_minutes=15,
    )

    assert snapshot["source"]["status"] == "healthy"
    assert snapshot["source"]["table"] == "dbo.xcelerator_review_orders"
    assert snapshot["summary"]["orders"] == 1
    assert snapshot["summary"]["pickup_on_time_pct"] == 1
    assert snapshot["summary"]["delivery_on_time_pct"] == 0
    assert snapshot["delivery_centers"][0]["delivery_late_orders"] == 1


def test_delivery_center_performance_snapshot_reports_missing_required_columns(monkeypatch):
    monkeypatch.setattr(service.FabricWarehouseSqlConfig, "from_env", lambda prefix: SimpleNamespace(configured=True))

    def fake_sql(config, query):
        if "GROUP BY schemas.name" in query:
            return [{"table_schema": "dbo", "table_name": "xcelerator_review_orders"}]
        if "columns.name AS column_name" in query:
            return [{"column_name": "Delivery Center"}]
        raise AssertionError("data query should not run when required columns are missing")

    monkeypatch.setattr(service, "execute_sql_query", fake_sql)

    snapshot = service.get_delivery_center_performance_snapshot(start="2026-05-01", end="2026-05-07")

    assert snapshot["source"]["status"] == "awaiting_feed"
    assert "pickup_date" in snapshot["source"]["missing_column_families"]
    assert snapshot["delivery_centers"] == []
