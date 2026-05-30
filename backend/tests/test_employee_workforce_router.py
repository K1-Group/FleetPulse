"""Tests for the read-only Employee Workforce API route."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from routers import employee_workforce  # noqa: E402


def test_employee_workforce_route_returns_read_only_projection(monkeypatch):
    monkeypatch.setattr(
        employee_workforce,
        "get_employee_workforce_dataset",
        lambda: {
            "projection_mode": "read_only",
            "source_authority": "Time Doctor employee time and activity export",
            "summary": {"employees": 0},
            "employees": [],
            "validation": {"status": "pending", "required_config": []},
        },
    )
    app = FastAPI()
    app.include_router(employee_workforce.router, prefix="/api/employee-workforce")

    response = TestClient(app).get("/api/employee-workforce")

    assert response.status_code == 200
    payload = response.json()
    assert payload["projection_mode"] == "read_only"
    assert payload["source_authority"] == "Time Doctor employee time and activity export"
    assert payload["summary"]["employees"] == 0
