"""Tests for fast K1L weekly engine-hour KPI projection."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services import k1l_weekly_engine_kpi_service as service  # noqa: E402


def test_route_lh_sql_uses_single_finish_column_without_coalesce():
    sql = service._warehouse_route_lh_sql(
        start=date(2026, 1, 1),
        end=date(2026, 1, 31),
        table_schema="dbo",
        table_name="xcelerator_review_orders",
        pickup_date_column="pickup_target_from",
        delivery_center_column="delivery_center",
        revenue_column="grand_total_amount",
        driver_pay_column="driver_pay_amount",
        service_column="service",
        route_column="route_no",
        start_column="pickup_target_from",
        finish_columns=["pod_datetime"],
    )

    assert "COALESCE(TRY_CONVERT(datetime2, [pod_datetime]))" not in sql
    assert "TRY_CONVERT(datetime2, [pod_datetime]) AS finish_at" in sql


def test_weekly_engine_kpi_allocates_cost_by_engine_hour(monkeypatch):
    def fake_operating_kpi():
        return {
            "source": "QBO + Xcelerator + AtoB + Geotab",
            "monthly": [{"month": "2026-05"}],
            "summary": {
                "revenue": 3000,
                "total_cost": 1800,
                "gross_profit": 1200,
            },
        }

    def fake_xcelerator_weekly(start, end, *, config):
        return (
            {
                "2026-05-04": {
                    **service._empty_entity_week(date(2026, 5, 4), date(2026, 5, 10)),
                    "k1l_orders": 2,
                    "k1l_grand_total": 900,
                    "k1l_driver_pay": 400,
                },
                "2026-05-11": {
                    **service._empty_entity_week(date(2026, 5, 11), date(2026, 5, 17)),
                    "k1l_orders": 3,
                    "k1l_grand_total": 2100,
                    "k1l_driver_pay": 700,
                },
            },
            {"status": "healthy", "source_authority": "Xcelerator", "projection_mode": "read_only", "row_count": 5},
            {},
            "fabric_warehouse_sql",
        )

    def fake_geotab_weekly(period_start, period_end):
        return (
            {
                "2026-05-04": {
                    "miles": 500,
                    "drive_hours": 8,
                    "idle_hours": 2,
                    "operating_hours": 10,
                    "trips": 4,
                },
                "2026-05-11": {
                    "miles": 900,
                    "drive_hours": 18,
                    "idle_hours": 2,
                    "operating_hours": 20,
                    "trips": 8,
                },
            },
            {"status": "healthy", "source_authority": "Geotab", "projection_mode": "read_only", "row_count": 2},
        )

    def fake_route_lh_weekly(start, end, *, config):
        return (
            {
                "2026-05-04": {
                    **service._empty_route_lh_week(date(2026, 5, 4), date(2026, 5, 10)),
                    "k1l_route_lh_orders": 1,
                    "k1l_route_lh_candidate_orders": 1,
                    "k1l_route_lh_revenue": 1200,
                    "k1l_route_lh_driver_pay": 500,
                    "k1l_route_lh_hours": 12,
                },
                "2026-05-11": {
                    **service._empty_route_lh_week(date(2026, 5, 11), date(2026, 5, 17)),
                    "k1l_route_lh_orders": 2,
                    "k1l_route_lh_candidate_orders": 2,
                    "k1l_route_lh_revenue": 2400,
                    "k1l_route_lh_driver_pay": 900,
                    "k1l_route_lh_hours": 18,
                },
            },
            {"status": "healthy", "source_authority": "Xcelerator route/LH", "projection_mode": "read_only", "row_count": 3},
        )

    monkeypatch.setattr(service, "get_k1l_operating_kpi_snapshot", fake_operating_kpi)
    monkeypatch.setattr(service, "_xcelerator_entity_weekly", fake_xcelerator_weekly)
    monkeypatch.setattr(service, "_recent_odata_geotab_weekly_metrics", fake_geotab_weekly)
    monkeypatch.setattr(service, "_load_xcelerator_route_lh_weekly", fake_route_lh_weekly)

    snapshot = service.get_k1l_weekly_engine_kpi_snapshot(start="2026-05-04", end="2026-05-17")

    assert snapshot["complete_k1l_engine_kpi_available"] is True
    assert snapshot["summary"]["operating_hours"] == 30
    assert snapshot["summary"]["k1l_revenue_per_engine_hour"] == 100
    assert snapshot["summary"]["k1l_true_operating_cost_per_engine_hour"] == 60
    assert snapshot["summary"]["k1l_profit_per_engine_hour"] == 40
    assert snapshot["summary"]["k1l_route_lh_orders"] == 3
    assert snapshot["summary"]["k1l_route_lh_revenue_per_hour"] == 120
    assert snapshot["summary"]["k1l_route_lh_driver_pay_per_hour"] == 46.6667
    assert snapshot["summary"]["k1l_route_lh_true_operating_cost_per_hour"] == 60
    assert snapshot["summary"]["k1l_route_lh_loaded_profit_per_hour"] == 60
    assert snapshot["weekly"][0]["k1l_true_operating_cost"] == 600
    assert snapshot["weekly"][1]["k1l_profit_per_engine_hour"] == 45
    assert snapshot["weekly"][1]["k1l_route_lh_driver_pay_per_hour"] == 50
    assert snapshot["weekly"][1]["k1l_route_lh_true_operating_cost_per_hour"] == 60
    assert snapshot["weekly"][1]["k1l_route_lh_profit_per_hour"] == 83.3333
    assert snapshot["weekly"][1]["k1l_route_lh_loaded_profit_per_hour"] == 73.3333
    assert snapshot["best_week"]["week_start"] == "2026-05-11"


def test_route_lh_weekly_applies_revenue_and_duration_rules():
    rows = [
        {
            "pickup_date": date(2026, 5, 4),
            "delivery_center": "K1 Logistics Inc",
            "revenue": 1200,
            "driver_pay": 600,
            "service": "LH",
            "route": "R1",
            "route_hours": 12,
        },
        {
            "pickup_date": date(2026, 5, 4),
            "delivery_center": "K1 Logistics Inc",
            "revenue": 999,
            "driver_pay": 300,
            "service": "LH",
            "route": "R2",
            "route_hours": 13,
        },
        {
            "pickup_date": date(2026, 5, 4),
            "delivery_center": "K1 Logistics Inc",
            "revenue": 1500,
            "driver_pay": 700,
            "service": "LH",
            "route": "R3",
            "route_hours": 11.5,
        },
        {
            "pickup_date": date(2026, 5, 4),
            "delivery_center": "K1 Logistics Inc",
            "revenue": 2000,
            "driver_pay": 800,
            "service": "Local",
            "route": "",
            "route_hours": 14,
        },
    ]

    weekly, source = service._route_lh_weekly_from_rows(rows, date(2026, 5, 4), date(2026, 5, 10))
    week = weekly["2026-05-04"]

    assert source["status"] == "healthy"
    assert source["row_count"] == 1
    assert week["k1l_route_lh_orders"] == 1
    assert week["k1l_route_lh_revenue"] == 1200
    assert week["k1l_route_lh_hours"] == 12
    assert week["k1l_route_lh_excluded_low_revenue_orders"] == 1
    assert week["k1l_route_lh_excluded_short_duration_orders"] == 1
    assert week["k1l_route_lh_excluded_non_route_lh_orders"] == 1
