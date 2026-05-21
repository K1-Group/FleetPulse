"""Delivery-center pickup and delivery on-time performance.

This projection is read-only. Xcelerator ReviewOrders remains the source of
truth for pickup/delivery target windows and actual lifecycle timestamps.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from configs.xcelerator_source import xcelerator_ceo_powerbi_only, xcelerator_source_label
from integrations.fabric_warehouse.sql_client import FabricWarehouseSqlConfig, execute_sql_query
from services.entity_margin_service import _coerce_date, _entity_from_delivery_center
from services.operating_cost_service import _resolve_window


DELIVERY_CENTER_PERFORMANCE_AUTHORITY = "K1 Group LLC / Xcelerator ReviewOrders pickup-delivery performance"
DEFAULT_ON_TIME_TOLERANCE_MINUTES = 15


def _source(status: str, *, message: str = "", row_count: int = 0) -> dict[str, Any]:
    return {
        "status": status,
        "source_authority": DELIVERY_CENTER_PERFORMANCE_AUTHORITY,
        "projection_mode": "read_only",
        "message": message,
        "row_count": row_count,
    }


def _quote_sql_identifier(value: str) -> str:
    return f"[{value.replace(']', ']]')}]"


def _quote_sql_literal(value: str) -> str:
    return f"'{value.replace(chr(39), chr(39) + chr(39))}'"


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


def _warehouse_table_discovery_sql() -> str:
    normalized_name = (
        "LOWER(REPLACE(REPLACE(REPLACE(REPLACE(columns.name, '[', ''), ']', ''), ' ', ''), '_', ''))"
    )
    return f"""
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
    SUM(CASE WHEN {normalized_name} IN ('deliverycenter') THEN 1 ELSE 0 END) > 0
    AND SUM(CASE WHEN {normalized_name} IN ('pickuptargetfrom', 'pfromdate', 'pfrom', 'fromdate') THEN 1 ELSE 0 END) > 0
ORDER BY
    CASE WHEN LOWER(objects.name) = 'xcelerator_review_orders' THEN 0 ELSE 1 END,
    CASE WHEN LOWER(objects.name) LIKE '%xcelerator%review%orders%' THEN 0 ELSE 1 END,
    schemas.name,
    objects.name
""".strip()


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


def _datetime_sql(column: str) -> str:
    return f"TRY_CONVERT(datetime2, {_quote_sql_identifier(column)})"


def _date_sql(column: str) -> str:
    return f"TRY_CONVERT(date, {_quote_sql_identifier(column)})"


def _coalesce_datetime_sql(columns: list[str]) -> str:
    expressions = [_datetime_sql(column) for column in columns]
    if not expressions:
        return "CAST(NULL AS datetime2)"
    if len(expressions) == 1:
        return expressions[0]
    return "COALESCE(" + ", ".join(expressions) + ")"


def _first_or_fallback(primary: list[str], fallback: str | None) -> list[str]:
    if primary:
        return primary
    return [fallback] if fallback else []


def _warehouse_performance_sql(
    *,
    table_schema: str,
    table_name: str,
    date_column: str,
    delivery_center_column: str,
    pickup_due_columns: list[str],
    pickup_actual_columns: list[str],
    delivery_due_columns: list[str],
    delivery_actual_columns: list[str],
    period_start: date,
    period_end: date,
) -> str:
    table_ref = f"{_quote_sql_identifier(table_schema)}.{_quote_sql_identifier(table_name)}"
    date_expr = _date_sql(date_column)
    return f"""
SELECT
    {date_expr} AS order_date,
    NULLIF(LTRIM(RTRIM(CONVERT(nvarchar(255), {_quote_sql_identifier(delivery_center_column)}))), '') AS delivery_center,
    {_coalesce_datetime_sql(pickup_due_columns)} AS pickup_due_at,
    {_coalesce_datetime_sql(pickup_actual_columns)} AS pickup_actual_at,
    {_coalesce_datetime_sql(delivery_due_columns)} AS delivery_due_at,
    {_coalesce_datetime_sql(delivery_actual_columns)} AS delivery_actual_at
FROM {table_ref}
WHERE {date_expr} >= '{period_start.isoformat()}'
    AND {date_expr} <= '{period_end.isoformat()}'
    AND {_quote_sql_identifier(delivery_center_column)} IS NOT NULL
""".strip()


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
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
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y %H:%M",
        "%m/%d/%y %H:%M",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%y %I:%M %p",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), 4)


def _empty_metric() -> dict[str, Any]:
    return {
        "orders": 0,
        "measured_orders": 0,
        "on_time_orders": 0,
        "late_orders": 0,
        "missing_orders": 0,
        "missing_schedule_orders": 0,
        "missing_actual_orders": 0,
        "total_late_minutes": 0.0,
        "max_late_minutes": 0.0,
    }


def _empty_center(delivery_center: str) -> dict[str, Any]:
    return {
        "delivery_center": delivery_center,
        "entity": _entity_from_delivery_center(delivery_center) or "Other / Unmapped",
        "orders": 0,
        "pickup": _empty_metric(),
        "delivery": _empty_metric(),
    }


def _accumulate_metric(
    metric: dict[str, Any],
    due_at: Any,
    actual_at: Any,
    *,
    tolerance_minutes: int,
) -> None:
    metric["orders"] += 1
    due = _parse_datetime(due_at)
    actual = _parse_datetime(actual_at)
    if not due:
        metric["missing_schedule_orders"] += 1
    if not actual:
        metric["missing_actual_orders"] += 1
    if not due or not actual:
        metric["missing_orders"] += 1
        return

    metric["measured_orders"] += 1
    delay_minutes = (actual - due).total_seconds() / 60
    if delay_minutes <= tolerance_minutes:
        metric["on_time_orders"] += 1
        return

    late_minutes = round(delay_minutes - tolerance_minutes, 1)
    metric["late_orders"] += 1
    metric["total_late_minutes"] += late_minutes
    metric["max_late_minutes"] = max(metric["max_late_minutes"], late_minutes)


def _finalize_metric(metric: dict[str, Any]) -> dict[str, Any]:
    measured = int(metric["measured_orders"])
    late = int(metric["late_orders"])
    orders = int(metric["orders"])
    total_late = float(metric.pop("total_late_minutes"))
    metric["on_time_pct"] = _ratio(metric["on_time_orders"], measured)
    metric["late_pct"] = _ratio(late, measured)
    metric["proof_coverage_pct"] = _ratio(measured, orders)
    metric["avg_late_minutes"] = round(total_late / late, 1) if late else (0.0 if measured else None)
    metric["max_late_minutes"] = round(float(metric["max_late_minutes"]), 1)
    return metric


def _flatten_center(center: dict[str, Any]) -> dict[str, Any]:
    pickup = _finalize_metric(center.pop("pickup"))
    delivery = _finalize_metric(center.pop("delivery"))
    return {
        **center,
        "pickup_orders": pickup["orders"],
        "pickup_measured_orders": pickup["measured_orders"],
        "pickup_on_time_orders": pickup["on_time_orders"],
        "pickup_late_orders": pickup["late_orders"],
        "pickup_missing_orders": pickup["missing_orders"],
        "pickup_missing_schedule_orders": pickup["missing_schedule_orders"],
        "pickup_missing_actual_orders": pickup["missing_actual_orders"],
        "pickup_on_time_pct": pickup["on_time_pct"],
        "pickup_late_pct": pickup["late_pct"],
        "pickup_proof_coverage_pct": pickup["proof_coverage_pct"],
        "pickup_avg_late_minutes": pickup["avg_late_minutes"],
        "pickup_max_late_minutes": pickup["max_late_minutes"],
        "delivery_orders": delivery["orders"],
        "delivery_measured_orders": delivery["measured_orders"],
        "delivery_on_time_orders": delivery["on_time_orders"],
        "delivery_late_orders": delivery["late_orders"],
        "delivery_missing_orders": delivery["missing_orders"],
        "delivery_missing_schedule_orders": delivery["missing_schedule_orders"],
        "delivery_missing_actual_orders": delivery["missing_actual_orders"],
        "delivery_on_time_pct": delivery["on_time_pct"],
        "delivery_late_pct": delivery["late_pct"],
        "delivery_proof_coverage_pct": delivery["proof_coverage_pct"],
        "delivery_avg_late_minutes": delivery["avg_late_minutes"],
        "delivery_max_late_minutes": delivery["max_late_minutes"],
    }


def _delivery_center_performance_from_rows(
    rows: list[dict[str, Any]],
    *,
    period_start: date,
    period_end: date,
    tolerance_minutes: int = DEFAULT_ON_TIME_TOLERANCE_MINUTES,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    centers: dict[str, dict[str, Any]] = {}
    summary = _empty_center("All delivery centers")

    for row in rows:
        row_day = _coerce_date(row.get("order_date"))
        if row_day is None or not (period_start <= row_day <= period_end):
            continue
        center_name = str(row.get("delivery_center") or "Unassigned").strip() or "Unassigned"
        center = centers.setdefault(center_name, _empty_center(center_name))
        center["orders"] += 1
        summary["orders"] += 1

        for bucket in (center, summary):
            _accumulate_metric(
                bucket["pickup"],
                row.get("pickup_due_at"),
                row.get("pickup_actual_at"),
                tolerance_minutes=tolerance_minutes,
            )
            _accumulate_metric(
                bucket["delivery"],
                row.get("delivery_due_at"),
                row.get("delivery_actual_at"),
                tolerance_minutes=tolerance_minutes,
            )

    center_rows = [_flatten_center(center) for center in centers.values()]
    center_rows.sort(key=lambda item: (-int(item["orders"]), item["delivery_center"]))
    summary_row = _flatten_center(summary)
    summary_row["delivery_center"] = "All delivery centers"
    summary_row["entity"] = "All"
    return center_rows, summary_row


def _column_resolution(columns: list[str]) -> tuple[dict[str, Any], list[str]]:
    pickup_date_column = _pick_column(
        columns,
        ("pickup_target_from", "[P]From Date", "PFrom Date", "From Date", "[P]From", "PFrom"),
    )
    delivery_center_column = _pick_column(columns, ("delivery_center", "Delivery Center", "DeliveryCenter"))
    pickup_from_column = _pick_column(
        columns,
        ("pickup_target_from", "[P]From", "PFrom", "Pickup Target From", "Pickup From"),
    )
    pickup_due_columns = _first_or_fallback(
        _pick_columns(columns, ("pickup_target_to", "[P]To", "PTo", "Pickup Target To", "Pickup To")),
        pickup_from_column,
    )
    pickup_actual_columns = _pick_columns(
        columns,
        (
            "p_arrival",
            "[P]Arrival",
            "PArrival",
            "Pickup Arrival",
            "pickup_arrival",
            "pickup_actual",
            "actual_pickup",
            "p_departure",
            "[P]Departure",
            "PDeparture",
            "Pickup Departure",
            "pickup_departure",
            "picked_up_at",
        ),
    )
    delivery_from_column = _pick_column(
        columns,
        ("delivery_target_from", "d_from", "[D]From", "DFrom", "Delivery Target From", "Delivery From"),
    )
    delivery_due_columns = _first_or_fallback(
        _pick_columns(columns, ("delivery_target_to", "d_to", "[D]To", "DTo", "Delivery Target To", "Delivery To")),
        delivery_from_column,
    )
    delivery_actual_columns = _pick_columns(
        columns,
        (
            "d_arrival",
            "[D]Arrival",
            "DArrival",
            "Delivery Arrival",
            "delivery_arrival",
            "actual_delivery",
            "delivery_actual",
            "d_departure",
            "[D]Departure",
            "DDeparture",
            "Delivery Departure",
            "pod_datetime",
            "POD DateTime",
            "PODDateTime",
            "rt_pod_datetime",
            "RT POD DateTime",
            "RT PODDateTime",
            "delivered_at",
        ),
    )

    resolution = {
        "date_column": pickup_date_column,
        "delivery_center_column": delivery_center_column,
        "pickup_due_columns": pickup_due_columns,
        "pickup_actual_columns": pickup_actual_columns,
        "delivery_due_columns": delivery_due_columns,
        "delivery_actual_columns": delivery_actual_columns,
    }
    missing = []
    if not pickup_date_column:
        missing.append("pickup_date")
    if not delivery_center_column:
        missing.append("delivery_center")
    if not pickup_due_columns:
        missing.append("pickup_target_window")
    if not pickup_actual_columns:
        missing.append("pickup_actual_timestamp")
    if not delivery_due_columns:
        missing.append("delivery_target_window")
    if not delivery_actual_columns:
        missing.append("delivery_actual_timestamp")
    return resolution, missing


def get_delivery_center_performance_snapshot(
    *,
    days: int = 370,
    start: date | datetime | str | None = None,
    end: date | datetime | str | None = None,
    tolerance_minutes: int = DEFAULT_ON_TIME_TOLERANCE_MINUTES,
) -> dict[str, Any]:
    period_start, period_end = _resolve_window(days, start, end)
    safe_tolerance = max(min(int(tolerance_minutes or DEFAULT_ON_TIME_TOLERANCE_MINUTES), 240), 0)
    base_payload: dict[str, Any] = {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_authority": DELIVERY_CENTER_PERFORMANCE_AUTHORITY,
        "projection_mode": "read_only",
        "grain": "delivery_center",
        "rules": {
            "on_time_tolerance_minutes": safe_tolerance,
            "pickup_actual_basis": "pickup arrival; falls back to pickup departure when arrival is unavailable",
            "delivery_actual_basis": "delivery arrival; falls back to delivery departure/POD when arrival is unavailable",
            "deadline_basis": "target-to timestamp; falls back to target-from timestamp when target-to is unavailable",
        },
        "summary": None,
        "delivery_centers": [],
    }

    if xcelerator_ceo_powerbi_only():
        return {
            **base_payload,
            "source": {
                **_source(
                    "awaiting_feed",
                    message="Delivery-center lifecycle performance is disabled until those timestamps are exposed by the Xcelerator CEO Dashboard semantic model.",
                ),
                "source_authority": xcelerator_source_label(),
            },
        }

    config = FabricWarehouseSqlConfig.from_env("FLEETPULSE_XCELERATOR_WAREHOUSE_SQL")
    if not config.configured:
        return {
            **base_payload,
            "source": _source(
                "not_configured",
                message="Fabric Warehouse SQL auth is not configured for Xcelerator ReviewOrders.",
            ),
        }

    try:
        table_rows = execute_sql_query(config, _warehouse_table_discovery_sql())
        if not table_rows:
            return {
                **base_payload,
                "source": _source(
                    "awaiting_feed",
                    message="No visible Xcelerator ReviewOrders table had delivery-center and pickup-date columns.",
                ),
            }

        table_schema = str(table_rows[0].get("table_schema") or "dbo")
        table_name = str(table_rows[0].get("table_name") or "xcelerator_review_orders")
        column_rows = execute_sql_query(config, _warehouse_columns_sql(table_schema, table_name))
        columns = [str(row.get("column_name") or "") for row in column_rows if row.get("column_name")]
        resolution, missing_columns = _column_resolution(columns)

        required_missing = [family for family in missing_columns if family in {"pickup_date", "delivery_center"}]
        if required_missing:
            return {
                **base_payload,
                "source": {
                    **_source(
                        "awaiting_feed",
                        message="Xcelerator ReviewOrders is missing required delivery-center performance columns.",
                    ),
                    "table": f"{table_schema}.{table_name}",
                    "missing_column_families": missing_columns,
                },
            }

        rows = execute_sql_query(
            config,
            _warehouse_performance_sql(
                table_schema=table_schema,
                table_name=table_name,
                date_column=str(resolution["date_column"]),
                delivery_center_column=str(resolution["delivery_center_column"]),
                pickup_due_columns=list(resolution["pickup_due_columns"]),
                pickup_actual_columns=list(resolution["pickup_actual_columns"]),
                delivery_due_columns=list(resolution["delivery_due_columns"]),
                delivery_actual_columns=list(resolution["delivery_actual_columns"]),
                period_start=period_start,
                period_end=period_end,
            ),
        )
    except Exception as exc:
        return {
            **base_payload,
            "source": _source("unavailable", message=f"{type(exc).__name__}: {exc}"),
        }

    delivery_centers, summary = _delivery_center_performance_from_rows(
        rows,
        period_start=period_start,
        period_end=period_end,
        tolerance_minutes=safe_tolerance,
    )
    measured_pickup = int(summary["pickup_measured_orders"]) if summary else 0
    measured_delivery = int(summary["delivery_measured_orders"]) if summary else 0
    row_count = int(summary["orders"]) if summary else 0
    source_status = "healthy" if measured_pickup and measured_delivery else "awaiting_feed"
    message = ""
    if row_count and not measured_pickup and not measured_delivery:
        message = "ReviewOrders rows loaded, but pickup/delivery target or actual timestamps are missing."
    elif row_count and (not measured_pickup or not measured_delivery):
        source_status = "partial"
        message = "ReviewOrders rows loaded with partial pickup/delivery timestamp proof."
    elif not row_count:
        message = "No ReviewOrders rows matched the requested period."
    if missing_columns and source_status == "healthy":
        source_status = "partial"
        message = "ReviewOrders rows loaded; some optional pickup/delivery column families were unavailable."

    return {
        **base_payload,
        "summary": summary,
        "delivery_centers": delivery_centers,
        "source": {
            **_source(source_status, message=message, row_count=row_count),
            "table": f"{table_schema}.{table_name}",
            "missing_column_families": missing_columns,
        },
    }
