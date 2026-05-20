"""Read-only Lane Stability API backed by the Fabric lakehouse KPI table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import os
import re
import time
from typing import Any

from integrations.fabric_warehouse.sql_client import (
    DEFAULT_ODBC_DRIVER,
    FabricWarehouseSqlConfig,
    execute_sql_query,
)


ALLOWED_WINDOWS = {42, 91, 182, 364}
MAX_WINDOW_DAYS = 1200
CACHE_TTL_SECONDS = 15 * 60
LANE_STABILITY_TABLE = "dbo.lane_stability_daily_kpi"

_SERVICE_COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CACHE: dict[tuple[int, str], tuple[float, dict[str, Any]]] = {}


@dataclass(frozen=True)
class LakehouseLaneStabilityConfig:
    """Runtime config for the K1 lakehouse lane stability projection."""

    sql: FabricWarehouseSqlConfig
    table_name: str = LANE_STABILITY_TABLE
    service_column: str = ""

    @classmethod
    def from_env(cls) -> "LakehouseLaneStabilityConfig":
        timeout_seconds = _int_env("LAKEHOUSE_SQL_TIMEOUT_SECONDS", 15)
        driver = os.getenv("LAKEHOUSE_SQL_ODBC_DRIVER", "").strip()
        return cls(
            sql=FabricWarehouseSqlConfig(
                server=(
                    os.getenv("LAKEHOUSE_SQL_SERVER", "").strip()
                    or os.getenv("FLEETPULSE_XCELERATOR_WAREHOUSE_SQL_SERVER", "").strip()
                ),
                database=(
                    os.getenv("LAKEHOUSE_SQL_DB", "").strip()
                    or os.getenv("FLEETPULSE_XCELERATOR_WAREHOUSE_SQL_DATABASE", "").strip()
                ),
                tenant_id=(
                    os.getenv("LAKEHOUSE_SP_TENANT", "").strip()
                    or os.getenv("FLEETPULSE_XCELERATOR_WAREHOUSE_SQL_TENANT_ID", "").strip()
                    or os.getenv("FLEETPULSE_GRAPH_TENANT_ID", "").strip()
                ),
                client_id=(
                    os.getenv("LAKEHOUSE_SP_CLIENT_ID", "").strip()
                    or os.getenv("FLEETPULSE_XCELERATOR_WAREHOUSE_SQL_CLIENT_ID", "").strip()
                    or os.getenv("FLEETPULSE_GRAPH_CLIENT_ID", "").strip()
                ),
                client_secret=(
                    os.getenv("LAKEHOUSE_SP_CLIENT_SECRET", "").strip()
                    or os.getenv("FLEETPULSE_XCELERATOR_WAREHOUSE_SQL_CLIENT_SECRET", "").strip()
                    or os.getenv("FLEETPULSE_GRAPH_CLIENT_SECRET", "").strip()
                ),
                driver=driver or DEFAULT_ODBC_DRIVER,
                timeout_seconds=timeout_seconds,
            ),
            table_name=os.getenv("LAKEHOUSE_LANE_STABILITY_TABLE", LANE_STABILITY_TABLE).strip()
            or LANE_STABILITY_TABLE,
            service_column=os.getenv("LAKEHOUSE_LANE_STABILITY_SERVICE_COLUMN", "").strip(),
        )


def _int_env(name: str, default: int) -> int:
    try:
        return max(int(os.getenv(name, str(default))), 1)
    except ValueError:
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clear_lane_stability_daily_cache() -> None:
    """Clear the in-memory response cache. Intended for tests and admin reloads."""

    _CACHE.clear()


def validate_window(window: int) -> int:
    if window > MAX_WINDOW_DAYS:
        raise ValueError(f"window must be <= {MAX_WINDOW_DAYS}")
    if window not in ALLOWED_WINDOWS:
        allowed = ", ".join(str(value) for value in sorted(ALLOWED_WINDOWS))
        raise ValueError(f"window must be one of {allowed}")
    return window


def _normalize_service(service: str | None) -> str:
    return (service or "").strip()


def _is_safe_table_name(table_name: str) -> bool:
    return all(_SERVICE_COLUMN_RE.fullmatch(part) for part in table_name.split("."))


def _build_query(config: LakehouseLaneStabilityConfig, service: str) -> tuple[str, tuple[Any, ...]]:
    if not _is_safe_table_name(config.table_name):
        raise RuntimeError("invalid_lane_stability_table_name")

    where_clauses = ["snapshot_date >= DATEADD(day, -?, CAST(GETDATE() AS date))"]
    params: list[Any] = []
    if service:
        service_column = config.service_column
        if not service_column:
            raise RuntimeError("lane_stability_service_filter_not_configured")
        if not _SERVICE_COLUMN_RE.fullmatch(service_column):
            raise RuntimeError("invalid_lane_stability_service_column")
        where_clauses.append(f"{service_column} = ?")
        params.append(service)

    sql = f"""
        SELECT
          snapshot_date,
          wtd_stable_cov_pct       AS stable_cov_pct,
          critical_lanes,
          cross_route_lanes,
          total_orders,
          total_lanes              AS scored_lanes,
          stable_lanes,
          total_revenue,
          delta_cov_pp
        FROM {config.table_name}
        WHERE {" AND ".join(where_clauses)}
        ORDER BY snapshot_date;
    """
    return sql, tuple(params)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _as_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return 0.0


def _as_int(value: Any) -> int:
    return int(round(_as_float(value)))


def _date_text(value: Any) -> str:
    safe = _json_safe(value)
    return str(safe or "")


def _normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "snapshot_date": _date_text(row.get("snapshot_date")),
                "stable_cov_pct": _as_float(row.get("stable_cov_pct")),
                "critical_lanes": _as_int(row.get("critical_lanes")),
                "cross_route_lanes": _as_int(row.get("cross_route_lanes")),
                "total_orders": _as_int(row.get("total_orders")),
                "scored_lanes": _as_int(row.get("scored_lanes")),
                "stable_lanes": _as_int(row.get("stable_lanes")),
                "total_revenue": round(_as_float(row.get("total_revenue")), 2),
                "delta_cov_pp": round(_as_float(row.get("delta_cov_pp")), 4),
            }
        )
    return normalized


def _compute_wow_delta(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    latest = rows[-1]
    explicit = latest.get("delta_cov_pp")
    if explicit not in (None, ""):
        return round(_as_float(explicit), 4)
    if len(rows) < 8:
        return 0.0
    return round(_as_float(latest.get("stable_cov_pct")) - _as_float(rows[-8].get("stable_cov_pct")), 4)


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "today_stable_cov_pct": 0.0,
            "wow_delta_pp": 0.0,
            "critical_today": 0,
            "cross_route_today": 0,
            "revenue_wtd": 0.0,
        }
    latest = rows[-1]
    return {
        "today_stable_cov_pct": _as_float(latest.get("stable_cov_pct")),
        "wow_delta_pp": _compute_wow_delta(rows),
        "critical_today": _as_int(latest.get("critical_lanes")),
        "cross_route_today": _as_int(latest.get("cross_route_lanes")),
        "revenue_wtd": round(_as_float(latest.get("total_revenue")), 2),
    }


def get_lane_stability_daily(
    *,
    window: int = 42,
    service: str | None = None,
    config: LakehouseLaneStabilityConfig | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Return daily lane stability rows from the governed Fabric lakehouse table."""

    window = validate_window(window)
    service_key = _normalize_service(service)
    cache_key = (window, service_key)
    now = time.time()
    if not force_refresh:
        cached = _CACHE.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]

    config = config or LakehouseLaneStabilityConfig.from_env()
    sql, query_params = _build_query(config, service_key)
    rows = _normalize_rows(execute_sql_query(config.sql, sql, (window, *query_params)))
    payload: dict[str, Any] = {
        "window": window,
        "generated_at": _now_iso(),
        "source_authority": "K1 Group LLC / Fabric lakehouse lane_stability_daily_kpi",
        "projection_mode": "read_only",
        "rows": rows,
        "summary": _summary(rows),
    }
    if service_key:
        payload["service"] = service_key

    _CACHE[cache_key] = (now + CACHE_TTL_SECONDS, payload)
    return payload
