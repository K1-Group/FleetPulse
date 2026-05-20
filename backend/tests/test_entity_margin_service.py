"""Tests for K1 entity CPM and gross-margin dashboard rollups."""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from integrations.fabric_warehouse.sql_client import FabricWarehouseSqlConfig  # noqa: E402
from integrations.powerbi.execute_queries import PowerBIExecuteQueriesConfig  # noqa: E402
from integrations.xcelerator.review_orders_feed import ReviewOrdersFeedConfig  # noqa: E402
from services import entity_margin_service as service  # noqa: E402


async def _fake_operating_cost_snapshot(days=90, start=None, end=None, **kwargs):
    assert kwargs.get("include_driver_pay") is False
    return {
        "period_start": str(start),
        "period_end": str(end),
        "generated_at": "2026-05-07T12:00:00+00:00",
        "sources": {
            "telemetry": {"status": "healthy", "source_authority": "Geotab", "row_count": 1},
            "fuel": {"status": "healthy", "source_authority": "AtoB", "row_count": 1},
            "qbo_expenses": {"status": "healthy", "source_authority": "QBO", "row_count": 2},
        },
        "weekly": [
            {
                "week_start": "2026-05-04",
                "week_end": "2026-05-06",
                "miles": 100.0,
                "drive_hours": 5.0,
                "idle_hours": 1.0,
                "operating_hours": 6.0,
                "fuel_cost": 100.0,
                "insurance_cost": 50.0,
                "other_expense_cost": 75.0,
            }
        ],
    }


def test_entity_margin_snapshot_keeps_k1l_cpm_and_k1g_margin_separate(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "get_operating_cost_snapshot", _fake_operating_cost_snapshot)
    review_orders = tmp_path / "review-orders.csv"
    review_orders.write_text(
        "\n".join(
            [
                "pickup_target_from,delivery_center,grand_total_amount,driver_pay_amount,order_tracking_id",
                "2026-05-04,K1 Logistics Inc,1000,250,L-1",
                '2026-05-05,"K1 Group, LLC",500,450,G-1',
                "2026-05-05,Test DC,999,999,T-1",
            ]
        ),
        encoding="utf-8",
    )
    config = service.EntityMarginConfig(
        powerbi=PowerBIExecuteQueriesConfig(),
        review_orders_feed=ReviewOrdersFeedConfig(path=str(review_orders)),
        warehouse_sql=FabricWarehouseSqlConfig(),
    )

    snapshot = asyncio.run(
        service.get_entity_margin_snapshot(
            start="2026-05-04",
            end="2026-05-05",
            config=config,
        )
    )

    summary = snapshot["summary"]
    assert snapshot["complete_k1l_cpm_available"] is True
    assert snapshot["complete_k1l_true_cpm_available"] is True
    assert snapshot["sources"]["xcelerator_entity"]["status"] == "healthy"
    assert snapshot["xcelerator_source_type"] == "review_orders_feed"
    assert snapshot["excluded_delivery_centers"] == {"Test DC": 1}
    assert summary["k1l_orders"] == 1
    assert summary["k1l_grand_total"] == 1000.0
    assert summary["k1l_driver_pay"] == 250.0
    assert summary["k1l_revenue_per_mile"] == 10.0
    assert summary["k1l_revenue_per_engine_hour"] == 166.6667
    assert summary["k1l_driver_pay_cpm"] == 2.5
    assert summary["k1l_fuel_plus_driver_cpm"] == 3.5
    assert summary["k1l_true_operating_cpm"] == 4.75
    assert summary["k1l_true_operating_cost_per_engine_hour"] == 79.1667
    assert summary["k1l_profit_per_engine_hour"] == 87.5
    assert summary["k1l_target_gross_margin"] == 720.0
    assert summary["k1l_actual_gross_margin_pct_before_fuel"] == 0.75
    assert summary["k1g_orders"] == 1
    assert summary["k1g_grand_total"] == 500.0
    assert summary["k1g_target_gross_margin"] == 100.0
    assert summary["k1g_actual_gross_margin_pct_before_overhead"] == 0.1
    assert "k1g_cost_per_mile" not in summary


def test_entity_margin_snapshot_uses_powerbi_semantic_model_when_configured(monkeypatch):
    monkeypatch.setattr(service, "get_operating_cost_snapshot", _fake_operating_cost_snapshot)

    def fake_execute_dax_query(config, query):
        assert "xcelerator_review_orders" in query
        return [
            {
                "[WeekStart]": "2026-05-04T00:00:00",
                "xcelerator_review_orders[delivery_center]": "K1 Logistics Inc",
                "[GrandTotal]": 1000,
                "[DriverPay]": 250,
                "[Orders]": 1,
            }
        ]

    monkeypatch.setattr(service, "execute_dax_query", fake_execute_dax_query)
    config = service.EntityMarginConfig(
        powerbi=PowerBIExecuteQueriesConfig(
            workspace_id="workspace",
            dataset_id="dataset",
            access_token="token",
        ),
        review_orders_feed=ReviewOrdersFeedConfig(),
        warehouse_sql=FabricWarehouseSqlConfig(),
    )

    snapshot = asyncio.run(
        service.get_entity_margin_snapshot(
            start="2026-05-04",
            end="2026-05-06",
            config=config,
        )
    )

    assert snapshot["xcelerator_source_type"] == "powerbi_semantic_model"
    assert snapshot["summary"]["k1l_grand_total"] == 1000.0
    assert snapshot["summary"]["k1l_fuel_plus_driver_cpm"] == 3.5


def test_powerbi_week_start_before_requested_start_is_included(monkeypatch):
    def fake_execute_dax_query(config, query):
        return [
            {
                "[WeekStart]": "2025-12-29T00:00:00",
                "xcelerator_review_orders[delivery_center]": "K1 Logistics Inc",
                "[GrandTotal]": 1200,
                "[DriverPay]": 300,
                "[Orders]": 2,
            }
        ]

    monkeypatch.setattr(service, "execute_dax_query", fake_execute_dax_query)
    config = service.EntityMarginConfig(
        powerbi=PowerBIExecuteQueriesConfig(
            workspace_id="workspace",
            dataset_id="dataset",
            access_token="token",
        ),
        review_orders_feed=ReviewOrdersFeedConfig(),
        warehouse_sql=FabricWarehouseSqlConfig(),
    )

    weekly, source, excluded, source_type = service._xcelerator_entity_weekly(
        date(2026, 1, 1),
        date(2026, 1, 4),
        config=config,
    )

    assert source["status"] == "healthy"
    assert source_type == "powerbi_semantic_model"
    assert excluded == {}
    assert weekly["2025-12-29"]["period_start"] == "2026-01-01"
    assert weekly["2025-12-29"]["k1l_orders"] == 2
    assert weekly["2025-12-29"]["k1l_grand_total"] == 1200.0


def test_entity_margin_snapshot_prefers_fabric_warehouse_sql(monkeypatch):
    monkeypatch.setattr(service, "get_operating_cost_snapshot", _fake_operating_cost_snapshot)

    def fake_execute_sql_query(config, query):
        if "sys.objects" in query:
            return [{"table_schema": "dbo", "table_name": "xcelerator_review_orders"}]
        assert "[dbo].[xcelerator_review_orders]" in query
        assert "driver_pay_amount" in query
        return [
            {
                "WeekStart": date(2026, 5, 4),
                "delivery_center": "K1 Logistics Inc",
                "GrandTotal": 1000,
                "DriverPay": 250,
                "Orders": 1,
            }
        ]

    monkeypatch.setattr(service, "execute_sql_query", fake_execute_sql_query)
    config = service.EntityMarginConfig(
        powerbi=PowerBIExecuteQueriesConfig(
            workspace_id="workspace",
            dataset_id="dataset",
            access_token="token",
        ),
        review_orders_feed=ReviewOrdersFeedConfig(),
        warehouse_sql=FabricWarehouseSqlConfig(
            server="server",
            database="database",
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
        ),
    )

    snapshot = asyncio.run(
        service.get_entity_margin_snapshot(
            start="2026-05-04",
            end="2026-05-06",
            config=config,
        )
    )

    assert snapshot["xcelerator_source_type"] == "fabric_warehouse_sql"
    assert snapshot["sources"]["xcelerator_entity"]["table"] == "dbo.xcelerator_review_orders"
    assert snapshot["summary"]["k1l_grand_total"] == 1000.0
    assert snapshot["summary"]["k1l_revenue_per_engine_hour"] == 166.6667


def test_entity_margin_snapshot_prefers_review_orders_feed_when_configured(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "get_operating_cost_snapshot", _fake_operating_cost_snapshot)
    monkeypatch.setenv("FLEETPULSE_XCELERATOR_ENTITY_MARGIN_PREFER_FEED", "true")

    def fail_execute_sql_query(config, query):
        raise AssertionError("Warehouse SQL should not be used when ReviewOrders feed preference is enabled")

    monkeypatch.setattr(service, "execute_sql_query", fail_execute_sql_query)
    review_orders = tmp_path / "review-orders.csv"
    review_orders.write_text(
        "\n".join(
            [
                "pickup_target_from,delivery_center,grand_total_amount,driver_pay_amount,order_tracking_id",
                "2026-05-04,K1 Logistics Inc,1000,250,L-1",
            ]
        ),
        encoding="utf-8",
    )
    config = service.EntityMarginConfig(
        powerbi=PowerBIExecuteQueriesConfig(),
        review_orders_feed=ReviewOrdersFeedConfig(path=str(review_orders)),
        warehouse_sql=FabricWarehouseSqlConfig(
            server="server",
            database="database",
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
        ),
    )

    snapshot = asyncio.run(
        service.get_entity_margin_snapshot(
            start="2026-05-04",
            end="2026-05-06",
            config=config,
        )
    )

    assert snapshot["xcelerator_source_type"] == "review_orders_feed"
    assert snapshot["summary"]["k1l_grand_total"] == 1000.0
