"""Tests for the read-only address benchmark API route."""

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

    def fake_dataset(pickup=None, delivery=None, route=None, days=None):
        calls.append({"pickup": pickup, "delivery": delivery, "route": route, "days": days})
        return {
            "projection_mode": "read_only",
            "source_authority": "Xcelerator ReviewOrders",
            "filters": {"pickup": pickup, "delivery": delivery, "route": route},
            "period": {"days": days},
            "summary": {"address_pairs": 0},
            "address_pairs": [],
        }

    monkeypatch.setattr(address_benchmarks, "get_address_benchmark_dataset", fake_dataset)
    app = FastAPI()
    app.include_router(address_benchmarks.router, prefix="/api/address-benchmarks")
    client = TestClient(app)
    client.dataset_calls = calls  # type: ignore[attr-defined]
    return client


def test_address_benchmark_route_passes_filters_to_read_only_service(monkeypatch):
    client = _client(monkeypatch)

    response = client.get(
        "/api/address-benchmarks?pickup=Fort%20Worth&delivery=Dallas&days=180"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["projection_mode"] == "read_only"
    assert payload["source_authority"] == "Xcelerator ReviewOrders"
    assert payload["filters"] == {"pickup": "Fort Worth", "delivery": "Dallas", "route": None}
    assert client.dataset_calls == [
        {"pickup": "Fort Worth", "delivery": "Dallas", "route": None, "days": 180}
    ]


def test_address_benchmark_route_trims_blank_filters(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/address-benchmarks?pickup=%20%20&delivery=%20Dallas%20")

    assert response.status_code == 200
    assert response.json()["filters"] == {"pickup": None, "delivery": "Dallas", "route": None}
    assert client.dataset_calls == [
        {"pickup": None, "delivery": "Dallas", "route": None, "days": None}
    ]


def test_address_benchmark_route_passes_xcelerator_route_filter(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/address-benchmarks?route=%20DFW%20001%20&days=180")

    assert response.status_code == 200
    assert response.json()["filters"]["route"] == "DFW 001"
    assert client.dataset_calls == [
        {"pickup": None, "delivery": None, "route": "DFW 001", "days": 180}
    ]


def test_address_benchmark_route_validates_history_window(monkeypatch):
    response = _client(monkeypatch).get("/api/address-benchmarks?days=731")

    assert response.status_code == 422
