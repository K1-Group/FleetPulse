"""Tests for the lakehouse-backed Lane Stability app endpoint."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from integrations.fabric_warehouse.sql_client import FabricWarehouseSqlConfig  # noqa: E402
from services import lakehouse_lane_stability_service as service  # noqa: E402


def _config() -> service.LakehouseLaneStabilityConfig:
    return service.LakehouseLaneStabilityConfig(
        sql=FabricWarehouseSqlConfig(
            server="lakehouse.example.fabric.microsoft.com",
            database="K1Lakehouse",
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
        )
    )


def test_lane_stability_daily_returns_summary_and_caches(monkeypatch):
    calls: list[tuple[str, tuple[object, ...] | None]] = []

    def fake_execute_sql_query(config, query, params=None):
        calls.append((query, params))
        return [
            {
                "snapshot_date": date(2026, 5, 11),
                "stable_cov_pct": 0.72,
                "critical_lanes": 4,
                "cross_route_lanes": 18,
                "total_orders": 220,
                "scored_lanes": 80,
                "stable_lanes": 58,
                "total_revenue": 101000.55,
                "delta_cov_pp": -1.2,
            },
            {
                "snapshot_date": date(2026, 5, 12),
                "stable_cov_pct": 0.7467,
                "critical_lanes": 3,
                "cross_route_lanes": 17,
                "total_orders": 240,
                "scored_lanes": 82,
                "stable_lanes": 61,
                "total_revenue": 120500.2,
                "delta_cov_pp": 2.4,
            },
        ]

    monkeypatch.setattr(service, "execute_sql_query", fake_execute_sql_query)
    service.clear_lane_stability_daily_cache()

    first = service.get_lane_stability_daily(window=42, config=_config())
    second = service.get_lane_stability_daily(window=42, config=_config())

    assert first is second
    assert first["window"] == 42
    assert first["projection_mode"] == "read_only"
    assert first["rows"][0]["snapshot_date"] == "2026-05-11"
    assert first["summary"] == {
        "today_stable_cov_pct": 0.7467,
        "wow_delta_pp": 2.4,
        "critical_today": 3,
        "cross_route_today": 17,
        "revenue_wtd": 120500.2,
    }
    assert len(calls) == 1
    assert calls[0][1] == (42,)
    assert "lane_stability_daily_kpi" in calls[0][0]


def test_lane_stability_daily_rejects_unknown_windows():
    with pytest.raises(ValueError, match="window must be one of"):
        service.get_lane_stability_daily(window=43, config=_config(), force_refresh=True)


def test_lane_stability_config_uses_existing_fabric_credentials(monkeypatch):
    monkeypatch.delenv("LAKEHOUSE_SQL_SERVER", raising=False)
    monkeypatch.delenv("LAKEHOUSE_SQL_DB", raising=False)
    monkeypatch.delenv("LAKEHOUSE_SP_TENANT", raising=False)
    monkeypatch.delenv("LAKEHOUSE_SP_CLIENT_ID", raising=False)
    monkeypatch.delenv("LAKEHOUSE_SP_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("FLEETPULSE_XCELERATOR_WAREHOUSE_SQL_SERVER", "warehouse.fabric.microsoft.com")
    monkeypatch.setenv("FLEETPULSE_XCELERATOR_WAREHOUSE_SQL_DATABASE", "K1-BI-WH")
    monkeypatch.setenv("FLEETPULSE_GRAPH_TENANT_ID", "tenant")
    monkeypatch.setenv("FLEETPULSE_GRAPH_CLIENT_ID", "client")
    monkeypatch.setenv("FLEETPULSE_GRAPH_CLIENT_SECRET", "secret")

    config = service.LakehouseLaneStabilityConfig.from_env()

    assert config.sql.server == "warehouse.fabric.microsoft.com"
    assert config.sql.database == "K1-BI-WH"
    assert config.sql.tenant_id == "tenant"
    assert config.sql.client_id == "client"
    assert config.sql.client_secret == "secret"


def test_lane_stability_daily_requires_service_column_for_service_filter():
    service.clear_lane_stability_daily_cache()

    with pytest.raises(RuntimeError, match="service_filter_not_configured"):
        service.get_lane_stability_daily(
            window=42,
            service="LH",
            config=_config(),
            force_refresh=True,
        )


def test_lane_stability_daily_applies_configured_service_filter(monkeypatch):
    captured: dict[str, object] = {}
    config = service.LakehouseLaneStabilityConfig(sql=_config().sql, service_column="service")

    def fake_execute_sql_query(config, query, params=None):
        captured["query"] = query
        captured["params"] = params
        return []

    monkeypatch.setattr(service, "execute_sql_query", fake_execute_sql_query)
    service.clear_lane_stability_daily_cache()

    payload = service.get_lane_stability_daily(window=91, service="LH", config=config)

    assert payload["service"] == "LH"
    assert captured["params"] == (91, "LH")
    assert "service = ?" in str(captured["query"])
