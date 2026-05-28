"""Tests for the FleetPulse address benchmark API route."""

from __future__ import annotations

import json
from pathlib import Path
import sys

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


def test_address_benchmarks_route_contract_hides_evidence_path(monkeypatch, tmp_path):
    state_path = tmp_path / "review-orders.json"
    evidence_path = tmp_path / "private-evidence.json"
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "processed_idempotency_keys": [],
                "last_imported_at": None,
                "rows": [
                    {
                        "OrderTrackingID": "RT-700",
                        "DriverNo": "D700",
                        "pickup_address": "Fort Worth Yard",
                        "delivery_address": "Dallas DC",
                        "pickup_departure": "2026-05-27T08:00:00Z",
                        "delivery_arrival": "2026-05-27T09:30:00Z",
                        "stop_minutes": "75",
                        "stop_geofence": "Dallas DC Dock",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    evidence_path.write_text(
        json.dumps(
            [
                {
                    "record_type": "email",
                    "load_id": "RT-700",
                    "service": "Outlook",
                    "subject": "Receiver delay",
                    "webLink": "https://outlook.example.test/messages/rt-700",
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("FLEETPULSE_ADDRESS_BENCHMARK_XCELERATOR_SOURCE", "review_orders_state")
    monkeypatch.setenv("FLEETPULSE_XCELERATOR_REVIEW_ORDERS_STATE_PATH", str(state_path))
    monkeypatch.setenv("FLEETPULSE_ADDRESS_BENCHMARK_EVIDENCE_PATH", str(evidence_path))
    monkeypatch.setenv("FLEETPULSE_ADDRESS_BENCHMARK_MIN_HISTORY_SAMPLES", "1")

    app = FastAPI()
    app.include_router(address_benchmarks.router, prefix="/api/address-benchmarks")
    response = TestClient(app).get("/api/address-benchmarks?days=30")

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision_summary"]["status"] == "ready"
    assert payload["evidence_sources"]["path_configured"] is True
    assert "path" not in payload["evidence_sources"]
    assert "path" not in payload["source_meta"]["evidence"]
    assert str(evidence_path) not in response.text
    assert payload["address_pairs"][0]["long_stop_evidence"][0]["stop_geofence"] == "Dallas DC Dock"


def test_address_benchmarks_full_app_returns_json_not_frontend_shell(monkeypatch, tmp_path):
    state_path = tmp_path / "review-orders.json"
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "processed_idempotency_keys": [],
                "last_imported_at": None,
                "rows": [
                    {
                        "OrderTrackingID": "RT-800",
                        "DriverNo": "D800",
                        "pickup_address": "Fort Worth Yard",
                        "delivery_address": "Dallas DC",
                        "pickup_departure": "2026-05-27T08:00:00Z",
                        "delivery_arrival": "2026-05-27T09:00:00Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("FLEETPULSE_ADDRESS_BENCHMARK_XCELERATOR_SOURCE", "review_orders_state")
    monkeypatch.setenv("FLEETPULSE_XCELERATOR_REVIEW_ORDERS_STATE_PATH", str(state_path))
    monkeypatch.setenv("FLEETPULSE_ADDRESS_BENCHMARK_MIN_HISTORY_SAMPLES", "1")
    monkeypatch.setenv("FLEETPULSE_ENTRA_AUTH_REQUIRED", "false")
    monkeypatch.setenv("FLEETPULSE_ENTRA_SEAT_ACCESS_ENFORCED", "false")

    from app import app as fleetpulse_app  # noqa: E402

    response = TestClient(fleetpulse_app).get("/api/address-benchmarks?days=30")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert not response.text.lstrip().startswith("<!DOCTYPE html>")
    payload = response.json()
    assert payload["projection_mode"] == "read_only"
    assert payload["source_meta"]["xcelerator"]["effective_xcelerator_source"] == "review_orders_state"
    assert payload["address_pairs"][0]["avg_route_minutes"] == 60.0
