"""Tests for dashboard API cache headers."""

from __future__ import annotations

import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from http_cache import DEFAULT_KPI_CACHE_CONTROL, api_cache_control_header  # noqa: E402


def test_cache_header_applies_to_connector_and_fuel_gets() -> None:
    assert (
        api_cache_control_header("GET", "/api/data-connector/vehicle-kpis", 200)
        == DEFAULT_KPI_CACHE_CONTROL
    )
    assert (
        api_cache_control_header("GET", "/api/fuel/operating-cost", 200)
        == DEFAULT_KPI_CACHE_CONTROL
    )


def test_cache_header_skips_mutations_errors_and_other_routes() -> None:
    assert api_cache_control_header("POST", "/api/fuel/atob/import", 200) is None
    assert api_cache_control_header("GET", "/api/fuel/summary", 500) is None
    assert api_cache_control_header("GET", "/api/dashboard/overview", 200) is None
