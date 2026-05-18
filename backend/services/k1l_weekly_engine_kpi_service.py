"""Fast K1L weekly engine-hour profitability projection.

This projection keeps source ownership read-only:

- Xcelerator Fabric Warehouse SQL provides weekly revenue/order facts.
- Geotab Fabric Warehouse SQL provides weekly miles and engine hours.
- The approved K1L operating KPI stack provides the total cost numerator.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from services.entity_margin_service import (
    EntityMarginConfig,
    K1G_MARGIN_TARGET_PCT,
    K1L_MARGIN_TARGET_PCT,
    _empty_entity_week,
    _xcelerator_entity_weekly,
)
from services.k1l_operating_kpi_service import get_k1l_operating_kpi_snapshot
from services.operating_cost_service import (
    GEOTAB_FABRIC_AUTHORITY,
    _geotab_warehouse_config_from_env,
    _resolve_window,
    _warehouse_geotab_weekly_metrics,
    _week_key,
    _week_windows,
)


WEEKLY_ENGINE_KPI_AUTHORITY = (
    "Xcelerator Fabric Warehouse revenue + Geotab Fabric Warehouse engine hours + "
    "approved K1L operating cost stack"
)


def _money(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value or 0), 2)


def _ratio(numerator: float | None, denominator: float | None, digits: int = 4) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), digits)


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _empty_source(status: str, authority: str, message: str = "") -> dict[str, Any]:
    return {
        "status": status,
        "source_authority": authority,
        "projection_mode": "read_only",
        "message": message,
        "row_count": 0,
    }


def _row_with_engine_kpis(
    row: dict[str, Any],
    *,
    total_cost_per_engine_hour: float | None,
) -> dict[str, Any]:
    revenue = _number(row.get("k1l_grand_total"))
    driver_pay = _number(row.get("k1l_driver_pay"))
    k1g_revenue = _number(row.get("k1g_grand_total"))
    k1g_driver_pay = _number(row.get("k1g_driver_pay"))
    miles = _number(row.get("miles"))
    drive_hours = _number(row.get("drive_hours"))
    operating_hours = _number(row.get("operating_hours") or drive_hours)
    allocated_cost = (
        round(total_cost_per_engine_hour * operating_hours, 2)
        if total_cost_per_engine_hour is not None and operating_hours > 0
        else None
    )
    profit = round(revenue - allocated_cost, 2) if allocated_cost is not None else None
    margin_before_fuel = revenue - driver_pay
    k1g_margin = k1g_revenue - k1g_driver_pay

    return {
        **row,
        "fuel_cost": 0.0,
        "insurance_cost": 0.0,
        "other_expense_cost": 0.0,
        "k1l_target_gross_margin": _money(revenue * K1L_MARGIN_TARGET_PCT),
        "k1l_actual_gross_margin_before_fuel": _money(margin_before_fuel),
        "k1l_actual_gross_margin_pct_before_fuel": _ratio(margin_before_fuel, revenue),
        "k1l_actual_gross_margin_after_fuel": _money(margin_before_fuel),
        "k1l_actual_gross_margin_pct_after_fuel": _ratio(margin_before_fuel, revenue),
        "k1l_revenue_per_mile": _ratio(revenue, miles, 3),
        "k1l_revenue_per_drive_hour": _ratio(revenue, drive_hours),
        "k1l_revenue_per_engine_hour": _ratio(revenue, operating_hours),
        "k1l_driver_pay_cpm": _ratio(driver_pay, miles, 3),
        "k1l_fuel_cpm": None,
        "k1l_fuel_plus_driver_cpm": _ratio(driver_pay, miles, 3),
        "k1l_true_operating_cpm": _ratio(allocated_cost, miles, 3),
        "k1l_true_operating_cost": allocated_cost,
        "k1l_true_operating_cost_per_drive_hour": _ratio(allocated_cost, drive_hours),
        "k1l_true_operating_cost_per_engine_hour": _ratio(allocated_cost, operating_hours),
        "k1l_profit": profit,
        "k1l_profit_per_mile": _ratio(profit, miles, 3),
        "k1l_profit_per_drive_hour": _ratio(profit, drive_hours),
        "k1l_profit_per_engine_hour": _ratio(profit, operating_hours),
        "k1g_target_gross_margin": _money(k1g_revenue * K1G_MARGIN_TARGET_PCT),
        "k1g_actual_gross_margin_before_overhead": _money(k1g_margin),
        "k1g_actual_gross_margin_pct_before_overhead": _ratio(k1g_margin, k1g_revenue),
        "qbo_expenses_available": allocated_cost is not None,
    }


def _summarize_weekly(rows: list[dict[str, Any]], operating_summary: dict[str, Any]) -> dict[str, Any]:
    revenue = _number(operating_summary.get("revenue"))
    total_cost = _number(operating_summary.get("total_cost"))
    gross_profit = _number(operating_summary.get("gross_profit"))
    miles = sum(_number(row.get("miles")) for row in rows)
    drive_hours = sum(_number(row.get("drive_hours")) for row in rows)
    idle_hours = sum(_number(row.get("idle_hours")) for row in rows)
    operating_hours = sum(_number(row.get("operating_hours")) for row in rows)
    k1l_orders = sum(int(_number(row.get("k1l_orders"))) for row in rows)
    k1g_orders = sum(int(_number(row.get("k1g_orders"))) for row in rows)
    k1l_driver_pay = sum(_number(row.get("k1l_driver_pay")) for row in rows)
    k1g_revenue = sum(_number(row.get("k1g_grand_total")) for row in rows)
    k1g_driver_pay = sum(_number(row.get("k1g_driver_pay")) for row in rows)

    row = {
        "miles": round(miles, 2),
        "drive_hours": round(drive_hours, 2),
        "idle_hours": round(idle_hours, 2),
        "operating_hours": round(operating_hours, 2),
        "fuel_cost": 0.0,
        "insurance_cost": 0.0,
        "other_expense_cost": 0.0,
        "k1l_orders": k1l_orders,
        "k1l_grand_total": _money(revenue),
        "k1l_driver_pay": _money(k1l_driver_pay),
        "k1g_orders": k1g_orders,
        "k1g_grand_total": _money(k1g_revenue),
        "k1g_driver_pay": _money(k1g_driver_pay),
        "qbo_expenses_available": operating_hours > 0,
    }
    return _row_with_engine_kpis(
        row,
        total_cost_per_engine_hour=_ratio(total_cost, operating_hours),
    ) | {
        "k1l_true_operating_cost": _money(total_cost),
        "k1l_profit": _money(gross_profit),
        "k1l_true_operating_cost_per_engine_hour": _ratio(total_cost, operating_hours),
        "k1l_profit_per_engine_hour": _ratio(gross_profit, operating_hours),
        "k1l_revenue_per_engine_hour": _ratio(revenue, operating_hours),
    }


def get_k1l_weekly_engine_kpi_snapshot(
    *,
    days: int = 370,
    start: date | datetime | str | None = None,
    end: date | datetime | str | None = None,
    config: EntityMarginConfig | None = None,
) -> dict[str, Any]:
    period_start, period_end = _resolve_window(days, start, end)
    weeks = _week_windows(period_start, period_end)
    config = config or EntityMarginConfig.from_env()

    operating_kpi = get_k1l_operating_kpi_snapshot()
    operating_summary = operating_kpi.get("summary") or {}
    total_cost = _number(operating_summary.get("total_cost"))

    entity_weekly, xcelerator_source, excluded_centers, xcelerator_source_type = _xcelerator_entity_weekly(
        period_start,
        period_end,
        config=config,
    )
    try:
        telemetry_weekly, telemetry_source = _warehouse_geotab_weekly_metrics(
            weeks,
            config=_geotab_warehouse_config_from_env(),
        )
    except Exception as exc:
        telemetry_weekly = {}
        telemetry_source = _empty_source(
            "unavailable",
            GEOTAB_FABRIC_AUTHORITY,
            f"{type(exc).__name__}: {exc}",
        )

    total_engine_hours = sum(_number(row.get("operating_hours")) for row in telemetry_weekly.values())
    total_cost_per_engine_hour = _ratio(total_cost, total_engine_hours)

    weekly_rows: list[dict[str, Any]] = []
    for week_start, week_end in weeks:
        key = _week_key(week_start)
        entity_row = entity_weekly.get(key, _empty_entity_week(week_start, week_end))
        telemetry_row = telemetry_weekly.get(key, {})
        row = {
            **entity_row,
            "miles": round(_number(telemetry_row.get("miles")), 2),
            "drive_hours": round(_number(telemetry_row.get("drive_hours")), 2),
            "idle_hours": round(_number(telemetry_row.get("idle_hours")), 2),
            "operating_hours": round(_number(telemetry_row.get("operating_hours")), 2),
        }
        weekly_rows.append(_row_with_engine_kpis(row, total_cost_per_engine_hour=total_cost_per_engine_hour))

    ranked_rows = [
        row for row in weekly_rows
        if _number(row.get("k1l_orders")) > 0 and row.get("k1l_profit_per_engine_hour") is not None
    ]
    best_week = max(ranked_rows, key=lambda row: _number(row.get("k1l_profit_per_engine_hour")), default=None)
    weakest_week = min(ranked_rows, key=lambda row: _number(row.get("k1l_profit_per_engine_hour")), default=None)
    sources = {
        "telemetry": telemetry_source,
        "xcelerator_entity": xcelerator_source,
        "operating_cost_stack": {
            "status": "healthy" if operating_summary else "awaiting_feed",
            "source_authority": str(operating_kpi.get("source") or "approved K1L operating cost stack"),
            "projection_mode": "read_only",
            "message": "",
            "row_count": len(operating_kpi.get("monthly") or []),
        },
    }
    unresolved_sources = [
        name for name, source in sources.items() if source.get("status") != "healthy"
    ]

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_authority": WEEKLY_ENGINE_KPI_AUTHORITY,
        "projection_mode": "read_only",
        "grain": "weekly",
        "complete_k1l_engine_kpi_available": not unresolved_sources and total_engine_hours > 0,
        "unresolved_sources": unresolved_sources,
        "xcelerator_source_type": xcelerator_source_type,
        "sources": sources,
        "summary": _summarize_weekly(weekly_rows, operating_summary),
        "weekly": weekly_rows,
        "best_week": best_week,
        "weakest_week": weakest_week,
        "excluded_delivery_centers": excluded_centers,
        "row_counts": {
            "weekly": len(weekly_rows),
            "ranked_weekly": len(ranked_rows),
            "excluded_delivery_centers": len(excluded_centers),
        },
    }
