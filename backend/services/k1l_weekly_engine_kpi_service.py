"""Fast K1L weekly engine-hour profitability projection.

This projection keeps source ownership read-only:

- Xcelerator Fabric Warehouse SQL provides weekly revenue/order facts.
- Geotab Fabric Warehouse SQL provides weekly miles and engine hours.
- The approved K1L operating KPI stack provides the total cost numerator.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any

from integrations.fabric_warehouse.sql_client import execute_sql_query
from services.entity_margin_service import (
    EntityMarginConfig,
    K1G_MARGIN_TARGET_PCT,
    K1L_MARGIN_TARGET_PCT,
    K1L_ENTITY,
    _coerce_date,
    _delivery_center,
    _empty_entity_week,
    _entity_from_delivery_center,
    _find_value,
    _grand_total,
    _driver_pay,
    _order_count,
    _xcelerator_entity_weekly,
)
from services.k1l_operating_kpi_service import get_k1l_operating_kpi_snapshot
from services.operating_cost_service import (
    GEOTAB_AUTHORITY,
    _accumulate_vehicle_kpi_row,
    _empty_week,
    _resolve_window,
    _source,
    _vehicle_kpi_day,
    _week_key,
    _week_windows,
)


WEEKLY_ENGINE_KPI_AUTHORITY = (
    "Xcelerator Fabric Warehouse revenue + Geotab Fabric Warehouse engine hours + "
    "approved K1L operating cost stack"
)
ROUTE_LH_EFFICIENCY_AUTHORITY = "K1 Group LLC / Xcelerator route/LH lifecycle efficiency"
ROUTE_LH_MIN_REVENUE = 1000.0
ROUTE_LH_MIN_HOURS = 12.0

_ROUTE_LH_ZERO_FIELDS = {
    "k1l_route_lh_orders": 0,
    "k1l_route_lh_candidate_orders": 0,
    "k1l_route_lh_revenue": 0.0,
    "k1l_route_lh_driver_pay": 0.0,
    "k1l_route_lh_hours": 0.0,
    "k1l_route_lh_excluded_non_route_lh_orders": 0,
    "k1l_route_lh_excluded_low_revenue_orders": 0,
    "k1l_route_lh_excluded_short_duration_orders": 0,
    "k1l_route_lh_excluded_missing_duration_orders": 0,
    "k1l_route_lh_excluded_revenue": 0.0,
}


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


def _quote_sql_identifier(value: str) -> str:
    return f"[{value.replace(']', ']]')}]"


def _quote_sql_literal(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _normalize_column(value: Any) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def _pick_column(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    normalized = {_normalize_column(column): column for column in columns}
    for alias in aliases:
        match = normalized.get(_normalize_column(alias))
        if match:
            return match
    return None


def _pick_columns(columns: list[str], aliases: tuple[str, ...]) -> list[str]:
    selected: list[str] = []
    for alias in aliases:
        column = _pick_column(columns, (alias,))
        if column and column not in selected:
            selected.append(column)
    return selected


def _warehouse_columns_sql(table_schema: str, table_name: str) -> str:
    return f"""
SELECT columns.name AS column_name
FROM sys.objects AS objects
JOIN sys.schemas AS schemas
    ON schemas.schema_id = objects.schema_id
JOIN sys.columns AS columns
    ON columns.object_id = objects.object_id
WHERE schemas.name = {_quote_sql_literal(table_schema)}
    AND objects.name = {_quote_sql_literal(table_name)}
ORDER BY columns.column_id
""".strip()


def _warehouse_table_discovery_sql() -> str:
    return """
SELECT TOP (10)
    schemas.name AS table_schema,
    objects.name AS table_name,
    objects.type_desc AS object_type
FROM sys.objects AS objects
JOIN sys.schemas AS schemas
    ON schemas.schema_id = objects.schema_id
JOIN sys.columns AS columns
    ON columns.object_id = objects.object_id
WHERE objects.type IN ('U', 'V', 'ET')
GROUP BY schemas.name, objects.name, objects.type_desc
HAVING
    SUM(CASE WHEN LOWER(columns.name) = 'delivery_center' THEN 1 ELSE 0 END) > 0
    AND SUM(CASE WHEN LOWER(columns.name) = 'pickup_target_from' THEN 1 ELSE 0 END) > 0
    AND SUM(CASE WHEN LOWER(columns.name) = 'grand_total_amount' THEN 1 ELSE 0 END) > 0
ORDER BY
    CASE WHEN LOWER(objects.name) = 'xcelerator_review_orders' THEN 0 ELSE 1 END,
    CASE WHEN LOWER(objects.name) LIKE '%xcelerator%review%orders%' THEN 0 ELSE 1 END,
    schemas.name,
    objects.name
""".strip()


def _datetime_sql(column: str) -> str:
    return f"TRY_CONVERT(datetime2, {_quote_sql_identifier(column)})"


def _warehouse_route_lh_sql(
    *,
    start: date,
    end: date,
    table_schema: str,
    table_name: str,
    pickup_date_column: str,
    delivery_center_column: str,
    revenue_column: str,
    driver_pay_column: str | None,
    service_column: str | None,
    route_column: str | None,
    start_column: str,
    finish_columns: list[str],
) -> str:
    table_ref = f"{_quote_sql_identifier(table_schema)}.{_quote_sql_identifier(table_name)}"
    pickup_date_expr = f"TRY_CONVERT(date, {_quote_sql_identifier(pickup_date_column)})"
    start_expr = _datetime_sql(start_column)
    finish_datetime_exprs = [_datetime_sql(column) for column in finish_columns]
    finish_expr = (
        finish_datetime_exprs[0]
        if len(finish_datetime_exprs) == 1
        else "COALESCE(" + ", ".join(finish_datetime_exprs) + ")"
    )
    driver_pay_expr = (
        f"TRY_CONVERT(decimal(18, 2), {_quote_sql_identifier(driver_pay_column)})"
        if driver_pay_column
        else "0"
    )
    service_expr = (
        f"CONVERT(nvarchar(255), {_quote_sql_identifier(service_column)})"
        if service_column
        else "''"
    )
    route_expr = (
        f"CONVERT(nvarchar(255), {_quote_sql_identifier(route_column)})"
        if route_column
        else "''"
    )
    return f"""
WITH normalized AS (
    SELECT
        {pickup_date_expr} AS pickup_date,
        CONVERT(nvarchar(255), {_quote_sql_identifier(delivery_center_column)}) AS delivery_center,
        TRY_CONVERT(decimal(18, 2), {_quote_sql_identifier(revenue_column)}) AS revenue,
        {driver_pay_expr} AS driver_pay,
        {service_expr} AS service,
        {route_expr} AS route,
        {start_expr} AS start_at,
        {finish_expr} AS finish_at
    FROM {table_ref}
    WHERE {pickup_date_expr} >= '{start.isoformat()}'
        AND {pickup_date_expr} <= '{end.isoformat()}'
        AND {_quote_sql_identifier(delivery_center_column)} IS NOT NULL
)
SELECT
    pickup_date,
    delivery_center,
    revenue,
    driver_pay,
    service,
    route,
    start_at,
    finish_at,
    CASE
        WHEN start_at IS NOT NULL AND finish_at IS NOT NULL AND finish_at > start_at
            THEN DATEDIFF(minute, start_at, finish_at) / 60.0
        ELSE NULL
    END AS route_hours
FROM normalized
WHERE pickup_date IS NOT NULL
""".strip()


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, (int, float)) and value > 20000:
        parsed_date = date(1899, 12, 30) + timedelta(days=int(value))
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day)
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y %H:%M", "%m/%d/%y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _route_lh_row_day(row: dict[str, Any]) -> date | None:
    return _coerce_date(
        _find_value(
            row,
            (
                "pickup_date",
                "PickupDate",
                "pickup_target_from",
                "[P]From Date",
                "PFrom Date",
                "From Date",
                "Order Date",
                "date",
            ),
        )
    )


def _route_lh_service(row: dict[str, Any]) -> str:
    return str(_find_value(row, ("service", "Service", "ServiceName", "Service Name")) or "").strip()


def _route_lh_route(row: dict[str, Any]) -> str:
    return str(_find_value(row, ("route", "Route", "RouteNo", "Route No", "route_no")) or "").strip()


def _route_lh_hours(row: dict[str, Any]) -> float | None:
    explicit = _find_value(row, ("route_hours", "RouteHours", "route_lh_hours"))
    if explicit not in (None, ""):
        value = _number(explicit)
        return value if value > 0 else None
    start_at = _parse_datetime(
        _find_value(row, ("start_at", "StartAt", "[P]From", "PFrom", "pickup_target_from"))
    )
    finish_at = _parse_datetime(
        _find_value(
            row,
            (
                "finish_at",
                "FinishAt",
                "[D]Departure",
                "DDeparture",
                "POD DateTime",
                "PODDateTime",
                "[D]To",
                "DTo",
            ),
        )
    )
    if not start_at or not finish_at or finish_at <= start_at:
        return None
    return round((finish_at - start_at).total_seconds() / 3600, 4)


def _is_route_lh_candidate(row: dict[str, Any]) -> bool:
    service = _normalize_column(_route_lh_service(row))
    route = _route_lh_route(row)
    return bool(route) or service in {"lh", "linehaul"} or "linehaul" in service


def _empty_route_lh_week(start: date, end: date) -> dict[str, Any]:
    return {
        "week_start": _week_key(start),
        "week_end": end.isoformat(),
        **_ROUTE_LH_ZERO_FIELDS,
    }


def _route_lh_weekly_from_rows(
    rows: list[dict[str, Any]],
    start: date,
    end: date,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    weekly = {
        _week_key(week_start): _empty_route_lh_week(week_start, week_end)
        for week_start, week_end in _week_windows(start, end)
    }
    k1l_seen = 0
    qualified = 0

    for row in rows:
        row_day = _route_lh_row_day(row)
        if row_day is None or not (start <= row_day <= end):
            continue
        if _entity_from_delivery_center(_delivery_center(row)) != K1L_ENTITY:
            continue

        k1l_seen += _order_count(row)
        bucket = weekly.setdefault(_week_key(row_day), _empty_route_lh_week(row_day, row_day))
        revenue = _grand_total(row)
        driver_pay = _driver_pay(row)
        route_hours = _route_lh_hours(row)
        route_lh_candidate = _is_route_lh_candidate(row)

        if not route_lh_candidate:
            bucket["k1l_route_lh_excluded_non_route_lh_orders"] += _order_count(row)
            bucket["k1l_route_lh_excluded_revenue"] += revenue
            continue

        bucket["k1l_route_lh_candidate_orders"] += _order_count(row)
        if revenue < ROUTE_LH_MIN_REVENUE:
            bucket["k1l_route_lh_excluded_low_revenue_orders"] += _order_count(row)
            bucket["k1l_route_lh_excluded_revenue"] += revenue
            continue
        if route_hours is None:
            bucket["k1l_route_lh_excluded_missing_duration_orders"] += _order_count(row)
            bucket["k1l_route_lh_excluded_revenue"] += revenue
            continue
        if route_hours < ROUTE_LH_MIN_HOURS:
            bucket["k1l_route_lh_excluded_short_duration_orders"] += _order_count(row)
            bucket["k1l_route_lh_excluded_revenue"] += revenue
            continue

        qualified += _order_count(row)
        bucket["k1l_route_lh_orders"] += _order_count(row)
        bucket["k1l_route_lh_revenue"] += revenue
        bucket["k1l_route_lh_driver_pay"] += driver_pay
        bucket["k1l_route_lh_hours"] += route_hours

    for bucket in weekly.values():
        bucket["k1l_route_lh_revenue"] = _money(bucket["k1l_route_lh_revenue"])
        bucket["k1l_route_lh_driver_pay"] = _money(bucket["k1l_route_lh_driver_pay"])
        bucket["k1l_route_lh_hours"] = round(float(bucket["k1l_route_lh_hours"] or 0), 2)
        bucket["k1l_route_lh_excluded_revenue"] = _money(bucket["k1l_route_lh_excluded_revenue"])

    status = "healthy" if qualified else "awaiting_feed" if k1l_seen else "awaiting_feed"
    message = ""
    if k1l_seen and not qualified:
        message = "K1L rows loaded, but none met the route/LH rule: revenue >= $1,000 and lifecycle >= 12 hours."
    elif not k1l_seen:
        message = "No K1L route/LH candidate rows were visible for the period."
    return weekly, _source(status, ROUTE_LH_EFFICIENCY_AUTHORITY, message=message, row_count=qualified)


def _load_xcelerator_route_lh_weekly(
    start: date,
    end: date,
    *,
    config: EntityMarginConfig,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if not config.warehouse_sql.configured:
        return {}, _empty_source(
            "not_configured",
            ROUTE_LH_EFFICIENCY_AUTHORITY,
            "Fabric Warehouse SQL auth is not configured for route/LH lifecycle efficiency.",
        )

    try:
        table_rows = execute_sql_query(config.warehouse_sql, _warehouse_table_discovery_sql())
        if not table_rows:
            return {}, _source(
                "awaiting_feed",
                ROUTE_LH_EFFICIENCY_AUTHORITY,
                message="No visible Xcelerator review-orders table had revenue/date columns.",
            )
        table_schema = str(table_rows[0].get("table_schema") or "dbo")
        table_name = str(table_rows[0].get("table_name") or "xcelerator_review_orders")
        column_rows = execute_sql_query(config.warehouse_sql, _warehouse_columns_sql(table_schema, table_name))
        columns = [str(row.get("column_name") or "") for row in column_rows if row.get("column_name")]

        pickup_date_column = _pick_column(columns, ("pickup_target_from", "[P]From Date", "PFrom Date", "From Date"))
        delivery_center_column = _pick_column(columns, ("delivery_center", "Delivery Center", "DeliveryCenter"))
        revenue_column = _pick_column(columns, ("grand_total_amount", "Grand Total", "GrandTotal", "Revenue"))
        driver_pay_column = _pick_column(columns, ("driver_pay_amount", "Driver Pay", "DriverPay", "driver_pay"))
        service_column = _pick_column(columns, ("service", "Service", "ServiceName", "Service Name"))
        route_column = _pick_column(columns, ("route_no", "RouteNo", "Route No", "route", "Route"))
        start_column = _pick_column(columns, ("p_from", "[P]From", "PFrom", "Pickup From", "pickup_target_from"))
        finish_columns = _pick_columns(
            columns,
            (
                "d_departure",
                "[D]Departure",
                "DDeparture",
                "Delivery Departure",
                "pod_datetime",
                "POD DateTime",
                "PODDateTime",
                "rt_pod_datetime",
                "RT POD DateTime",
                "d_to",
                "[D]To",
                "DTo",
                "Delivery To",
            ),
        )
        if not pickup_date_column or not delivery_center_column or not revenue_column:
            return {}, _source(
                "awaiting_feed",
                ROUTE_LH_EFFICIENCY_AUTHORITY,
                message="Xcelerator table is missing required route/LH revenue/date columns.",
            )
        if not start_column or not finish_columns:
            return {}, _source(
                "awaiting_feed",
                ROUTE_LH_EFFICIENCY_AUTHORITY,
                message="Xcelerator table is missing start/finish lifecycle columns for the 12-hour rule.",
            )

        rows = execute_sql_query(
            config.warehouse_sql,
            _warehouse_route_lh_sql(
                start=start,
                end=end,
                table_schema=table_schema,
                table_name=table_name,
                pickup_date_column=pickup_date_column,
                delivery_center_column=delivery_center_column,
                revenue_column=revenue_column,
                driver_pay_column=driver_pay_column,
                service_column=service_column,
                route_column=route_column,
                start_column=start_column,
                finish_columns=finish_columns,
            ),
        )
    except Exception as exc:
        return {}, _source(
            "unavailable",
            ROUTE_LH_EFFICIENCY_AUTHORITY,
            message=f"{type(exc).__name__}: {exc}",
        )

    weekly, source = _route_lh_weekly_from_rows(rows, start, end)
    source["table"] = f"{table_schema}.{table_name}"
    source["rules"] = "route/LH rows only; revenue >= $1,000; lifecycle >= 12 hours"
    return weekly, source


def _recent_odata_geotab_weekly_metrics(
    period_start: date,
    period_end: date,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    from routers import data_connector

    rows = asyncio.run(
        data_connector._odata_get(  # noqa: SLF001 - bounded read-only fallback.
            "VehicleKpi_Daily",
            search="last_90_day",
            top=1000,
        )
    )
    metrics: dict[str, dict[str, Any]] = {}
    included_dates: list[date] = []
    for row in rows:
        row_day = _vehicle_kpi_day(row)
        if row_day is None or not (period_start <= row_day <= period_end):
            continue
        included_dates.append(row_day)
        bucket = metrics.setdefault(_week_key(row_day), _empty_week(row_day, row_day))
        _accumulate_vehicle_kpi_row(bucket, row)

    for bucket in metrics.values():
        bucket["miles"] = round(bucket["miles"], 2)
        bucket["drive_hours"] = round(bucket["drive_hours"], 2)
        bucket["idle_hours"] = round(bucket["idle_hours"], 2)
        bucket["operating_hours"] = round(bucket["drive_hours"] + bucket["idle_hours"], 2)

    if not metrics:
        return {}, _source(
            "awaiting_feed",
            GEOTAB_AUTHORITY,
            message="Geotab Data Connector returned no recent VehicleKpi_Daily rows.",
        )

    status = "healthy"
    message = ""
    if min(included_dates) > period_start:
        status = "partial"
        message = (
            f"Geotab Data Connector fallback covers {min(included_dates).isoformat()}.."
            f"{max(included_dates).isoformat()}; earlier YTD weeks remain pending."
        )
    return metrics, _source(status, GEOTAB_AUTHORITY, message=message, row_count=len(included_dates))


def _fast_geotab_weekly_metrics(
    weeks: list[tuple[date, date]],
    *,
    period_start: date,
    period_end: date,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    try:
        return _recent_odata_geotab_weekly_metrics(period_start, period_end)
    except Exception as odata_exc:
        return {}, _empty_source(
            "unavailable",
            GEOTAB_AUTHORITY,
            f"{type(odata_exc).__name__}: {odata_exc}",
        )


def _row_with_engine_kpis(
    row: dict[str, Any],
    *,
    total_cost_per_engine_hour: float | None,
    total_cost_per_route_lh_hour: float | None = None,
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
    route_lh_revenue = _number(row.get("k1l_route_lh_revenue"))
    route_lh_driver_pay = _number(row.get("k1l_route_lh_driver_pay"))
    route_lh_hours = _number(row.get("k1l_route_lh_hours"))
    route_lh_allocated_cost = (
        round(total_cost_per_route_lh_hour * route_lh_hours, 2)
        if total_cost_per_route_lh_hour is not None and route_lh_hours > 0
        else None
    )
    route_lh_profit = (
        round(route_lh_revenue - route_lh_allocated_cost, 2)
        if route_lh_allocated_cost is not None
        else None
    )

    return {
        **row,
        **{field: row.get(field, default) for field, default in _ROUTE_LH_ZERO_FIELDS.items()},
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
        "k1l_route_lh_target_revenue": ROUTE_LH_MIN_REVENUE,
        "k1l_route_lh_target_hours": ROUTE_LH_MIN_HOURS,
        "k1l_route_lh_revenue_per_hour": _ratio(route_lh_revenue, route_lh_hours),
        "k1l_route_lh_driver_pay_per_hour": _ratio(route_lh_driver_pay, route_lh_hours),
        "k1l_route_lh_true_operating_cost": route_lh_allocated_cost,
        "k1l_route_lh_true_operating_cost_per_hour": _ratio(route_lh_allocated_cost, route_lh_hours),
        "k1l_route_lh_profit": route_lh_profit,
        "k1l_route_lh_profit_per_hour": _ratio(route_lh_profit, route_lh_hours),
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
    route_lh_totals = {
        field: sum(_number(row.get(field)) for row in rows)
        for field in _ROUTE_LH_ZERO_FIELDS
    }

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
        **{
            field: int(value)
            if field.endswith("_orders")
            else _money(value)
            if field.endswith("_revenue") or field.endswith("_pay")
            else round(float(value or 0), 2)
            for field, value in route_lh_totals.items()
        },
    }
    return _row_with_engine_kpis(
        row,
        total_cost_per_engine_hour=_ratio(total_cost, operating_hours),
        total_cost_per_route_lh_hour=_ratio(total_cost, route_lh_totals["k1l_route_lh_hours"]),
    ) | {
        "k1l_true_operating_cost": _money(total_cost),
        "k1l_profit": _money(gross_profit),
        "k1l_true_operating_cost_per_engine_hour": _ratio(total_cost, operating_hours),
        "k1l_profit_per_engine_hour": _ratio(gross_profit, operating_hours),
        "k1l_revenue_per_engine_hour": _ratio(revenue, operating_hours),
        "k1l_route_lh_true_operating_cost": _money(total_cost)
        if route_lh_totals["k1l_route_lh_hours"] > 0
        else None,
        "k1l_route_lh_true_operating_cost_per_hour": _ratio(total_cost, route_lh_totals["k1l_route_lh_hours"]),
        "k1l_route_lh_profit": _money(route_lh_totals["k1l_route_lh_revenue"] - total_cost)
        if route_lh_totals["k1l_route_lh_hours"] > 0
        else None,
        "k1l_route_lh_profit_per_hour": _ratio(
            route_lh_totals["k1l_route_lh_revenue"] - total_cost,
            route_lh_totals["k1l_route_lh_hours"],
        ),
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
    route_lh_weekly, route_lh_source = _load_xcelerator_route_lh_weekly(
        period_start,
        period_end,
        config=config,
    )
    telemetry_weekly, telemetry_source = _fast_geotab_weekly_metrics(
        weeks,
        period_start=period_start,
        period_end=period_end,
    )

    total_engine_hours = sum(_number(row.get("operating_hours")) for row in telemetry_weekly.values())
    total_cost_per_engine_hour = _ratio(total_cost, total_engine_hours)
    total_route_lh_hours = sum(_number(row.get("k1l_route_lh_hours")) for row in route_lh_weekly.values())
    total_cost_per_route_lh_hour = _ratio(total_cost, total_route_lh_hours)

    weekly_rows: list[dict[str, Any]] = []
    for week_start, week_end in weeks:
        key = _week_key(week_start)
        entity_row = entity_weekly.get(key, _empty_entity_week(week_start, week_end))
        telemetry_row = telemetry_weekly.get(key, {})
        route_lh_row = route_lh_weekly.get(key, _empty_route_lh_week(week_start, week_end))
        row = {
            **entity_row,
            **{field: route_lh_row.get(field, default) for field, default in _ROUTE_LH_ZERO_FIELDS.items()},
            "miles": round(_number(telemetry_row.get("miles")), 2),
            "drive_hours": round(_number(telemetry_row.get("drive_hours")), 2),
            "idle_hours": round(_number(telemetry_row.get("idle_hours")), 2),
            "operating_hours": round(_number(telemetry_row.get("operating_hours")), 2),
        }
        weekly_rows.append(
            _row_with_engine_kpis(
                row,
                total_cost_per_engine_hour=total_cost_per_engine_hour,
                total_cost_per_route_lh_hour=total_cost_per_route_lh_hour,
            )
        )

    ranked_rows = [
        row for row in weekly_rows
        if _number(row.get("k1l_route_lh_orders")) > 0 and row.get("k1l_route_lh_profit_per_hour") is not None
    ]
    best_week = max(ranked_rows, key=lambda row: _number(row.get("k1l_route_lh_profit_per_hour")), default=None)
    weakest_week = min(ranked_rows, key=lambda row: _number(row.get("k1l_route_lh_profit_per_hour")), default=None)
    sources = {
        "telemetry": telemetry_source,
        "xcelerator_entity": xcelerator_source,
        "xcelerator_route_lh_efficiency": route_lh_source,
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
        "efficiency_basis": "route_lh_qualified",
        "efficiency_rules": {
            "scope": "K1L route/LH rows only",
            "min_revenue": ROUTE_LH_MIN_REVENUE,
            "min_lifecycle_hours": ROUTE_LH_MIN_HOURS,
            "hour_window": "Xcelerator pickup start to delivery finish",
            "cost_allocation": "approved K1L cost stack allocated by qualified route/LH lifecycle-hour share",
        },
        "complete_k1l_engine_kpi_available": not unresolved_sources and total_engine_hours > 0 and total_route_lh_hours > 0,
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
