"""Tests for the FleetPulse Lane Stability API route."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from routers import lane_stability  # noqa: E402


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr(
        lane_stability,
        "get_lane_stability_daily",
        lambda window=42, service=None: {
            "window": window,
            "service": service,
            "generated_at": "2026-05-19T12:00:00+00:00",
            "projection_mode": "read_only",
            "rows": [
                {
                    "snapshot_date": "2026-05-19",
                    "stable_cov_pct": 0.81,
                    "critical_lanes": 2,
                    "cross_route_lanes": 7,
                    "total_orders": 120,
                    "scored_lanes": 48,
                    "stable_lanes": 39,
                    "total_revenue": 50000.0,
                    "delta_cov_pp": 1.5,
                }
            ],
            "summary": {
                "today_stable_cov_pct": 0.81,
                "wow_delta_pp": 1.5,
                "critical_today": 2,
                "cross_route_today": 7,
                "revenue_wtd": 50000.0,
            },
        },
    )
    app = FastAPI()
    app.include_router(lane_stability.router, prefix="/api/lane-stability")
    return TestClient(app)


def test_lane_stability_route_returns_daily_payload(monkeypatch):
    response = _client(monkeypatch).get("/api/lane-stability?window=42&service=LH")

    assert response.status_code == 200
    payload = response.json()
    assert payload["window"] == 42
    assert payload["service"] == "LH"
    assert payload["summary"]["today_stable_cov_pct"] == 0.81
    assert payload["rows"][0]["snapshot_date"] == "2026-05-19"


def test_lane_stability_route_validates_window(monkeypatch):
    response = _client(monkeypatch).get("/api/lane-stability?window=1201")

    assert response.status_code == 422


def test_lane_stability_route_returns_unified_scorecard(monkeypatch):
    monkeypatch.setattr(
        lane_stability,
        "get_unified_route_lh_scorecard",
        lambda: {
            "generated_at": "2026-05-31T12:00:00+00:00",
            "period_end": "2026-05-23",
            "projection_mode": "read_only",
            "feed_status": "healthy",
            "summary": {"missed_hour_revenue": 89879.35},
            "items": [],
            "gap_detail": {"status": "healthy", "total_windows": 197, "windows": []},
            "source_boundaries": [],
        },
    )

    response = _client(monkeypatch).get("/api/lane-stability/unified-scorecard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["period_end"] == "2026-05-23"
    assert payload["projection_mode"] == "read_only"
    assert payload["summary"]["missed_hour_revenue"] == 89879.35
    assert payload["gap_detail"]["total_windows"] == 197
