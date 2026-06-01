"""Tests for the read-only Driver Compliance API route."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from routers import driver_compliance  # noqa: E402


def test_driver_compliance_route_returns_read_only_projection(monkeypatch):
    monkeypatch.setattr(
        driver_compliance,
        "get_driver_compliance_dataset",
        lambda: {
            "projection_mode": "read_only",
            "source_authority": "Configured driver qualification document register",
            "summary": {"drivers": 0},
            "document_types": [
                {"key": "medical_card", "label": "Medical Card", "warning_days": 45},
                {"key": "drug_test", "label": "Drug Test", "warning_days": 45},
                {"key": "mvr", "label": "MVR", "warning_days": 45},
            ],
            "drivers": [],
            "validation": {"status": "pending", "required_config": []},
        },
    )
    app = FastAPI()
    app.include_router(driver_compliance.router, prefix="/api/driver-compliance")

    response = TestClient(app).get("/api/driver-compliance")

    assert response.status_code == 200
    payload = response.json()
    assert payload["projection_mode"] == "read_only"
    assert payload["summary"]["drivers"] == 0
    assert [item["key"] for item in payload["document_types"]] == ["medical_card", "drug_test", "mvr"]
