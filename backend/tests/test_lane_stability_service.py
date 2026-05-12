"""Tests for Xcelerator lane stability scoring."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make backend/ importable regardless of how pytest is invoked.
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from integrations.xcelerator.review_orders_feed import ReviewOrdersFeedConfig  # noqa: E402
from services.lane_stability_service import LaneStabilityConfig, get_lane_stability_snapshot  # noqa: E402


def _row(
    service: str,
    lane: str,
    driver: str,
    route: str,
    revenue: float,
    gm: float,
    driver_pay: float,
    day: str = "05/09/2026",
) -> dict:
    return {
        "[P]From Date": day,
        "Service": service,
        "Ref#": lane,
        "DriverNo": driver,
        "RouteNo": route,
        "Grand Total": revenue,
        "Gross Margin($)": gm,
        "Driver Pay": driver_pay,
    }


def _write_json(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps({"rows": rows}), encoding="utf-8")


def test_lane_stability_uses_xcelerator_footer_for_company_revenue(tmp_path):
    current_path = tmp_path / "current.json"
    baseline_path = tmp_path / "baseline.json"
    _write_json(
        current_path,
        [
            _row("LH", "HDS K1", "D1", "DFW 001", 100, 60, 40),
            _row("LH", "HDS K1", "D2", "DFW 001", 100, 60, 40),
            _row("LH", "HDS K1", "D1", "DFW 002", 100, 60, 40),
            _row("LH", "SB Pay ticket", "D3", "DFW 003", 250, 250, 0),
            _row("ATL-ShipBob", "ATL 1", "D4", "ATL 001", 300, 200, 100),
            {"Grand Total": 1000.0, "Gross Margin($)": 700.0, "Driver Pay": 300.0},
        ],
    )
    _write_json(
        baseline_path,
        [
            _row("LH", "HDS K1", "D1", "DFW 001", 100, 60, 40, "04/15/2026"),
            _row("LH", "HDS K1", "D1", "DFW 001", 100, 60, 40, "04/16/2026"),
            _row("LH", "HDS K1", "D1", "DFW 001", 100, 60, 40, "04/17/2026"),
        ],
    )
    config = LaneStabilityConfig(
        order_feed=ReviewOrdersFeedConfig(path=str(current_path)),
        baseline_feed=ReviewOrdersFeedConfig(path=str(baseline_path)),
        excluded_scoring_services=("ATL-ShipBob",),
        excluded_scoring_ref_patterns=("pay ticket", "route ticket", "tonu", "service-only"),
    )

    snapshot = get_lane_stability_snapshot(days=7, config=config)

    assert snapshot["company_kpis"]["total_revenue"] == 1000.0
    assert snapshot["company_kpis"]["total_revenue_source"] == "xcelerator_footer"
    assert snapshot["company_kpis"]["team_subset_revenue"] == 300.0
    assert snapshot["company_kpis"]["total_lanes"] == 1
    assert snapshot["company_kpis"]["cross_route_lanes"] == 1
    assert snapshot["lanes"][0]["stable_cov_pct"] == 0.6667
    assert snapshot["lanes"][0]["status"] == "At Risk"
    assert snapshot["lanes"][0]["primary_route"] == "DFW 001"
    assert len(snapshot["routes"]) == 2
    assert snapshot["trend"][0]["trend_type"] == "degrading"


def test_lane_stability_returns_awaiting_feed_when_unconfigured():
    config = LaneStabilityConfig(
        order_feed=ReviewOrdersFeedConfig(),
        baseline_feed=ReviewOrdersFeedConfig(),
        excluded_scoring_services=(),
        excluded_scoring_ref_patterns=(),
    )

    snapshot = get_lane_stability_snapshot(days=7, config=config)

    assert snapshot["feed_status"] == "awaiting_feed"
    assert snapshot["company_kpis"]["projection_mode"] == "read_only"
    assert snapshot["company_kpis"]["source_authority"] == "K1 Group LLC / Xcelerator"


def test_lane_stability_accepts_live_axis_order_aliases(tmp_path):
    current_path = tmp_path / "axis-current.json"
    _write_json(
        current_path,
        [
            {
                "oDate": "2026-05-11T00:00:00",
                "ServiceName": "LH",
                "ClientRefNo": "BM FTW-OKC",
                "DriverNo": "345",
                "RouteNo": "DHL 001",
                "GrandTotal": 761.0,
                "OrderCharge": 761.0,
            },
            {
                "oDate": "2026-05-11T00:00:00",
                "ServiceName": "LH",
                "ClientRefNo": "BM FTW-OKC",
                "DriverNo": "346",
                "RouteNo": "DHL 002",
                "GrandTotal": 500.0,
                "OrderCharge": 500.0,
            },
        ],
    )
    config = LaneStabilityConfig(
        order_feed=ReviewOrdersFeedConfig(path=str(current_path)),
        baseline_feed=ReviewOrdersFeedConfig(),
        excluded_scoring_services=("ATL-ShipBob",),
        excluded_scoring_ref_patterns=("pay ticket", "route ticket", "tonu", "service-only"),
    )

    snapshot = get_lane_stability_snapshot(days=1, config=config)

    assert snapshot["period_start"] == "2026-05-11"
    assert snapshot["company_kpis"]["total_revenue"] == 1261.0
    assert snapshot["company_kpis"]["total_revenue_source"] == "row_sum"
    assert snapshot["lanes"][0]["service"] == "LH"
    assert snapshot["lanes"][0]["lane"] == "BM FTW-OKC"
    assert snapshot["lanes"][0]["cross_route"] is True
