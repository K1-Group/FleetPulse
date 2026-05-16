"""Tests for fast Xcelerator gross-margin dashboard rollups."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from integrations.xcelerator.review_orders_feed import ReviewOrdersFeedConfig  # noqa: E402
from services.xcelerator_gross_margin_service import get_xcelerator_gross_margin_snapshot  # noqa: E402


def test_gross_margin_snapshot_uses_xcelerator_gross_margin_field(tmp_path):
    review_orders = tmp_path / "review-orders.csv"
    review_orders.write_text(
        "\n".join(
            [
                "[P]From Date,Delivery Center,Grand Total,Driver Pay,Gross Margin($),OrderTrackingID",
                "2026-05-04,K1 Logistics Inc,1000,250,760,L-1",
                '2026-05-05,"K1 Group, LLC",500,450,50,G-1',
                "2026-05-05,Test DC,999,999,0,T-1",
            ]
        ),
        encoding="utf-8",
    )

    snapshot = get_xcelerator_gross_margin_snapshot(
        start="2026-05-01",
        end="2026-05-10",
        config=ReviewOrdersFeedConfig(path=str(review_orders)),
    )

    assert snapshot["status"] == "partial"
    assert snapshot["summary"]["orders"] == 2
    assert snapshot["summary"]["revenue"] == 1500.0
    assert snapshot["summary"]["driver_pay"] == 700.0
    assert snapshot["summary"]["gross_margin"] == 810.0
    assert snapshot["summary"]["gross_margin_pct"] == 0.54
    assert snapshot["excluded_row_count"] == 1
    assert snapshot["source_method"] == "xcelerator_gross_margin_field"
    assert {row["entity"] for row in snapshot["entities"]} == {"K1 Logistics Inc", "K1 Group LLC"}
    assert snapshot["weekly"][0]["week_start"] == "2026-05-04"
    assert snapshot["monthly"][0]["month_start"] == "2026-05-01"
    assert snapshot["monthly"][0]["revenue"] == 1500.0
    assert snapshot["monthly"][0]["gross_margin"] == 810.0


def test_gross_margin_snapshot_falls_back_to_revenue_minus_driver_pay(tmp_path):
    review_orders = tmp_path / "review-orders.json"
    review_orders.write_text(
        """
        {"rows":[
          {
            "[P]From Date":"2026-05-04",
            "Delivery Center":"K1 Logistics Inc",
            "Grand Total":"$1,000.00",
            "Driver Pay":"$250.00",
            "OrderTrackingID":"L-1"
          }
        ]}
        """,
        encoding="utf-8",
    )

    snapshot = get_xcelerator_gross_margin_snapshot(
        start="2026-05-04",
        end="2026-05-04",
        config=ReviewOrdersFeedConfig(path=str(review_orders)),
    )

    assert snapshot["status"] == "healthy"
    assert snapshot["summary"]["gross_margin"] == 750.0
    assert snapshot["summary"]["gross_margin_pct"] == 0.75
    assert snapshot["source_method"] == "revenue_minus_driver_pay"


def test_large_json_requires_summary_cache_for_dashboard_request(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEETPULSE_GROSS_MARGIN_REQUEST_REBUILD_MAX_BYTES", "1")
    review_orders = tmp_path / "review-orders.json"
    review_orders.write_text('{"rows":[', encoding="utf-8")

    snapshot = get_xcelerator_gross_margin_snapshot(
        start="2026-05-04",
        end="2026-05-04",
        config=ReviewOrdersFeedConfig(path=str(review_orders)),
    )

    assert snapshot["status"] == "awaiting_feed"
    assert snapshot["source_method"] == "summary_cache_missing"
    assert "not summarized inside dashboard requests" in snapshot["message"]


def test_large_non_json_path_requires_summary_cache_for_dashboard_request(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEETPULSE_GROSS_MARGIN_REQUEST_REBUILD_MAX_BYTES", "1")
    review_orders = tmp_path / "review-orders.csv"
    review_orders.write_text(
        "\n".join(
            [
                "[P]From Date,Delivery Center,Grand Total,Driver Pay,Gross Margin($)",
                "2026-05-04,K1 Logistics Inc,1000,250,750",
            ]
        ),
        encoding="utf-8",
    )

    snapshot = get_xcelerator_gross_margin_snapshot(
        start="2026-05-04",
        end="2026-05-04",
        config=ReviewOrdersFeedConfig(path=str(review_orders)),
    )

    assert snapshot["status"] == "awaiting_feed"
    assert snapshot["source_method"] == "summary_cache_missing"


def test_url_feed_requires_summary_cache_for_dashboard_request(monkeypatch):
    monkeypatch.delenv("FLEETPULSE_GROSS_MARGIN_ALLOW_REQUEST_REBUILD", raising=False)

    snapshot = get_xcelerator_gross_margin_snapshot(
        start="2026-05-04",
        end="2026-05-04",
        config=ReviewOrdersFeedConfig(url="https://example.invalid/review-orders.json"),
    )

    assert snapshot["status"] == "awaiting_feed"
    assert snapshot["source_method"] == "summary_cache_missing"
