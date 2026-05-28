"""Tests for the FleetPulse address benchmark API route."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from routers import address_benchmarks  # noqa: E402


def _client(monkeypatch) -> TestClient:
    calls: list[dict[str, object]] = []

    def fake_dataset(*, pickup=None, delivery=None, days=None):
        calls.append({"pickup": pickup, "delivery": delivery, "days": days})
        return {
            "projection_mode": "read_only",
            "source_authority": "K1 Group LLC / Xcelerator ReviewOrders rows + configured voice/email evidence",
            "filters": {"pickup": pickup, "delivery": delivery},
            "period": {"days": days},
            "thresholds": {"stop_threshold_minutes": 60},
            "summary": {"address_pairs": 0, "measured_orders": 0},
            "address_pairs": [],
        }

    monkeypatch.setattr(address_benchmarks, "get_address_benchmark_dataset", fake_dataset)
    app = FastAPI()
    app.include_router(address_benchmarks.router, prefix="/api/address-benchmarks")
    client = TestClient(app)
    client.calls = calls  # type: ignore[attr-defined]
    return client


def test_address_benchmarks_route_passes_filters_and_returns_json(monkeypatch):
    client = _client(monkeypatch)

    response = client.get(
        "/api/address-benchmarks",
        params={"pickup": "Fort Worth Yard", "delivery": "Dallas DC", "days": 180},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert client.calls == [  # type: ignore[attr-defined]
        {"pickup": "Fort Worth Yard", "delivery": "Dallas DC", "days": 180}
    ]
    payload = response.json()
    assert payload["projection_mode"] == "read_only"
    assert payload["filters"] == {"pickup": "Fort Worth Yard", "delivery": "Dallas DC"}
    assert payload["thresholds"]["stop_threshold_minutes"] == 60


def test_address_benchmarks_route_validates_days(monkeypatch):
    response = _client(monkeypatch).get("/api/address-benchmarks?days=731")

    assert response.status_code == 422
