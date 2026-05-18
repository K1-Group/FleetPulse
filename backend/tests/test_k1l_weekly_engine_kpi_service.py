"""Tests for fast K1L weekly engine-hour KPI projection."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services import k1l_weekly_engine_kpi_service as service  # noqa: E402


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

    def fake_geotab_weekly(weeks, *, config):
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

    monkeypatch.setattr(service, "get_k1l_operating_kpi_snapshot", fake_operating_kpi)
    monkeypatch.setattr(service, "_xcelerator_entity_weekly", fake_xcelerator_weekly)
    monkeypatch.setattr(service, "_warehouse_geotab_weekly_metrics", fake_geotab_weekly)

    snapshot = service.get_k1l_weekly_engine_kpi_snapshot(start="2026-05-04", end="2026-05-17")

    assert snapshot["complete_k1l_engine_kpi_available"] is True
    assert snapshot["summary"]["operating_hours"] == 30
    assert snapshot["summary"]["k1l_revenue_per_engine_hour"] == 100
    assert snapshot["summary"]["k1l_true_operating_cost_per_engine_hour"] == 60
    assert snapshot["summary"]["k1l_profit_per_engine_hour"] == 40
    assert snapshot["weekly"][0]["k1l_true_operating_cost"] == 600
    assert snapshot["weekly"][1]["k1l_profit_per_engine_hour"] == 45
    assert snapshot["best_week"]["week_start"] == "2026-05-11"
