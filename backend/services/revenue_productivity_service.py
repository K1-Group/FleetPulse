"""Revenue productivity KPIs for the Vehicle Efficiency panel.

The metric boundaries stay read-only:

- Xcelerator Fabric Warehouse SQL supplies K1L revenue and dispatch drivers.
- Geotab supplies active truck counts from the same 7-day utilization window.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from geotab_client import GeotabClient
from integrations.fabric_warehouse.sql_client import FabricWarehouseSqlConfig, execute_sql_query
from services.entity_margin_service import K1L_ENTITY, _entity_from_delivery_center


XCELERATOR_AUTHORITY = "K1 Group LLC / Xcelerator review orders"
GEOTAB_AUTHORITY = "K1 Logistics Inc / Geotab trips"
TARGET_REVENUE_PER_DRIVER_WEEK = 5000.0
TARGET_REVENUE_PER_TRUCK_WEEK = 7000.0


def _quote_sql_identifier(value: str) -> str:
    return f"[{value.replace(']', ']]')}]"


def _source(status: str, authority: str, *, message: str = "", row_count: int = 0) -> dict[str, Any]:
    return {
        "status": status,
        "source_authority": authority,
        "projection_mode": "read_only",
        "message": message,
        "row_count": row_count,
    }


def _money(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _ratio(numerator: float | None, denominator: int | float | None) -> float | None:
    if numerator is None or denominator is None or float(denominator) <= 0:
        return None
    return round(float(numerator) / float(denominator), 2)


def _target_status(value: float | None, target: float) -> str:
    if value is None:
        return "pending"
    return "above_target" if value >= target else "below_target"


def _target_delta(value: float | None, target: float) -> float | None:
    if value is None:
        return None
    return _money(value - target)


def _normalize_column(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def _pick_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    by_exact = {column.casefold(): column for column in columns}
    for candidate in candidates:
        match = by_exact.get(candidate.casefold())
        if match:
            return match

    by_normalized = {_normalize_column(column): column for column in columns}
    for candidate in candidates:
        match = by_normalized.get(_normalize_column(candidate))
        if match:
            return match
    return None


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


def _warehouse_columns_sql(table_schema: str, table_name: str) -> str:
    return f"""
SELECT columns.name AS column_name
FROM sys.objects AS objects
JOIN sys.schemas AS schemas
    ON schemas.schema_id = objects.schema_id
JOIN sys.columns AS columns
    ON columns.object_id = objects.object_id
WHERE schemas.name = '{table_schema.replace("'", "''")}'
    AND objects.name = '{table_name.replace("'", "''")}'
ORDER BY columns.column_id
""".strip()


def _warehouse_productivity_sql(
    *,
    table_schema: str,
    table_name: str,
    pickup_column: str,
    delivery_center_column: str,
    revenue_column: str,
    driver_column: str | None,
    period_start: date,
    period_end: date,
) -> str:
    table_ref = f"{_quote_sql_identifier(table_schema)}.{_quote_sql_identifier(table_name)}"
    driver_expr = (
        f"NULLIF(LTRIM(RTRIM(CONVERT(nvarchar(255), {_quote_sql_identifier(driver_column)}))), '')"
        if driver_column
        else "NULL"
    )
    return f"""
SELECT
    TRY_CONVERT(date, {_quote_sql_identifier(pickup_column)}) AS pickup_date,
    CONVERT(nvarchar(255), {_quote_sql_identifier(delivery_center_column)}) AS delivery_center,
    TRY_CONVERT(decimal(18, 2), {_quote_sql_identifier(revenue_column)}) AS revenue,
    {driver_expr} AS driver_key
FROM {table_ref}
WHERE TRY_CONVERT(date, {_quote_sql_identifier(pickup_column)}) >= '{period_start.isoformat()}'
    AND TRY_CONVERT(date, {_quote_sql_identifier(pickup_column)}) <= '{period_end.isoformat()}'
    AND {_quote_sql_identifier(delivery_center_column)} IS NOT NULL
""".strip()


def _load_xcelerator_productivity(
    period_start: date,
    period_end: date,
) -> dict[str, Any]:
    config = FabricWarehouseSqlConfig.from_env("FLEETPULSE_XCELERATOR_WAREHOUSE_SQL")
    if not config.configured:
        return {
            "revenue": None,
            "driver_count": None,
            "driver_source": "unavailable",
            "sources": {
                "revenue": _source(
                    "not_configured",
                    XCELERATOR_AUTHORITY,
                    message="Fabric Warehouse SQL is not configured.",
                ),
                "drivers": _source(
                    "not_configured",
                    XCELERATOR_AUTHORITY,
                    message="Fabric Warehouse SQL is not configured.",
                ),
            },
            "table": None,
        }

    try:
        table_rows = execute_sql_query(config, _warehouse_table_discovery_sql())
        if not table_rows:
            awaiting = _source(
                "awaiting_feed",
                XCELERATOR_AUTHORITY,
                message="No visible Xcelerator review-orders table had revenue/date columns.",
            )
            return {
                "revenue": None,
                "driver_count": None,
                "driver_source": "unavailable",
                "sources": {"revenue": awaiting, "drivers": awaiting},
                "table": None,
            }

        table = table_rows[0]
        table_schema = str(table.get("table_schema") or "dbo")
        table_name = str(table.get("table_name") or "xcelerator_review_orders")
        column_rows = execute_sql_query(config, _warehouse_columns_sql(table_schema, table_name))
        columns = [str(row.get("column_name") or "") for row in column_rows if row.get("column_name")]

        pickup_column = _pick_column(columns, ("pickup_target_from", "Pickup Target From", "PickupTargetFrom"))
        delivery_column = _pick_column(columns, ("delivery_center", "Delivery Center", "DeliveryCenter"))
        revenue_column = _pick_column(columns, ("grand_total_amount", "Grand Total", "GrandTotal", "Revenue"))
        driver_column = _pick_column(
            columns,
            (
                "driver_no",
                "DriverNo",
                "Driver No",
                "driver",
                "Driver",
                "driver_name",
                "Driver Name",
                "driver_id",
            ),
        )
        if not pickup_column or not delivery_column or not revenue_column:
            unavailable = _source(
                "unavailable",
                XCELERATOR_AUTHORITY,
                message="Xcelerator review-orders table is missing required revenue/date columns.",
            )
            return {
                "revenue": None,
                "driver_count": None,
                "driver_source": "unavailable",
                "sources": {"revenue": unavailable, "drivers": unavailable},
                "table": f"{table_schema}.{table_name}",
            }

        rows = execute_sql_query(
            config,
            _warehouse_productivity_sql(
                table_schema=table_schema,
                table_name=table_name,
                pickup_column=pickup_column,
                delivery_center_column=delivery_column,
                revenue_column=revenue_column,
                driver_column=driver_column,
                period_start=period_start,
                period_end=period_end,
            ),
        )
    except Exception as exc:
        unavailable = _source("unavailable", XCELERATOR_AUTHORITY, message=f"{type(exc).__name__}: {exc}")
        return {
            "revenue": None,
            "driver_count": None,
            "driver_source": "unavailable",
            "sources": {"revenue": unavailable, "drivers": unavailable},
            "table": None,
        }

    revenue = 0.0
    driver_keys: set[str] = set()
    included_rows = 0
    for row in rows:
        if _entity_from_delivery_center(row.get("delivery_center")) != K1L_ENTITY:
            continue
        included_rows += 1
        try:
            revenue += float(row.get("revenue") or 0)
        except (TypeError, ValueError):
            pass
        driver_key = str(row.get("driver_key") or "").strip()
        if driver_key:
            driver_keys.add(driver_key.casefold())

    revenue_source = _source(
        "healthy" if included_rows else "awaiting_feed",
        XCELERATOR_AUTHORITY,
        message="" if included_rows else "No K1 Logistics Inc review-order rows matched the period.",
        row_count=included_rows,
    )
    driver_source = _source(
        "healthy" if driver_keys else "awaiting_feed",
        XCELERATOR_AUTHORITY,
        message="" if driver_keys else "No dispatch driver column/values were available for the period.",
        row_count=len(driver_keys),
    )
    return {
        "revenue": _money(revenue) if included_rows else None,
        "driver_count": len(driver_keys) or None,
        "driver_source": "xcelerator_review_orders" if driver_keys else "unavailable",
        "sources": {"revenue": revenue_source, "drivers": driver_source},
        "table": f"{table_schema}.{table_name}",
    }


def _trip_driver_key(trip: dict[str, Any]) -> str | None:
    driver = trip.get("driver")
    if not isinstance(driver, dict):
        return None
    value = driver.get("id") or driver.get("name")
    if not value:
        return None
    text = str(value).strip()
    if not text or text.casefold() in {"unknown", "none"}:
        return None
    return text.casefold()


def _load_geotab_activity(period_start_dt: datetime, period_end_dt: datetime) -> dict[str, Any]:
    try:
        client = GeotabClient.get()
        trips = client.get_trips(from_date=period_start_dt, to_date=period_end_dt)
    except Exception as exc:
        return {
            "truck_count": None,
            "driver_count": None,
            "sources": {
                "trucks": _source("unavailable", GEOTAB_AUTHORITY, message=f"{type(exc).__name__}: {exc}"),
                "geotab_drivers": _source("unavailable", GEOTAB_AUTHORITY, message=f"{type(exc).__name__}: {exc}"),
            },
        }

    device_miles: dict[str, float] = {}
    driver_keys: set[str] = set()
    for trip in trips:
        device = trip.get("device")
        if isinstance(device, dict):
            device_id = str(device.get("id") or "").strip()
            if device_id:
                try:
                    device_miles[device_id] = device_miles.get(device_id, 0.0) + float(trip.get("distance") or 0) * 0.621371
                except (TypeError, ValueError):
                    pass
        driver_key = _trip_driver_key(trip)
        if driver_key:
            driver_keys.add(driver_key)

    active_trucks = {device_id for device_id, miles in device_miles.items() if miles >= 10}
    return {
        "truck_count": len(active_trucks),
        "driver_count": len(driver_keys) or None,
        "sources": {
            "trucks": _source(
                "healthy" if active_trucks else "awaiting_feed",
                GEOTAB_AUTHORITY,
                message="" if active_trucks else "No Geotab trucks exceeded 10 miles in the period.",
                row_count=len(active_trucks),
            ),
            "geotab_drivers": _source(
                "healthy" if driver_keys else "awaiting_feed",
                GEOTAB_AUTHORITY,
                message="" if driver_keys else "No Geotab trip driver assignments were present in the period.",
                row_count=len(driver_keys),
            ),
        },
    }


def get_revenue_productivity_snapshot(days: int = 7) -> dict[str, Any]:
    period_days = max(min(int(days or 7), 31), 1)
    period_end_dt = datetime.now(timezone.utc)
    period_start_dt = period_end_dt - timedelta(days=period_days)
    period_start = period_start_dt.date()
    period_end = period_end_dt.date()

    geotab = _load_geotab_activity(period_start_dt, period_end_dt)
    xcelerator = _load_xcelerator_productivity(period_start, period_end)

    revenue = xcelerator.get("revenue")
    truck_count = geotab.get("truck_count")
    driver_count = xcelerator.get("driver_count") or geotab.get("driver_count")
    driver_source = xcelerator.get("driver_source")
    driver_source_payload = xcelerator["sources"]["drivers"]
    if not xcelerator.get("driver_count") and geotab.get("driver_count"):
        driver_source = "geotab_trip_driver_fallback"
        driver_source_payload = geotab["sources"]["geotab_drivers"]

    revenue_per_truck = _ratio(revenue, truck_count)
    revenue_per_driver = _ratio(revenue, driver_count)

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "period_days": period_days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "projection_mode": "read_only",
        "source_authority": "Xcelerator revenue + Geotab active trucks",
        "targets": {
            "revenue_per_driver_week": TARGET_REVENUE_PER_DRIVER_WEEK,
            "revenue_per_truck_week": TARGET_REVENUE_PER_TRUCK_WEEK,
        },
        "summary": {
            "revenue": revenue,
            "truck_count": truck_count,
            "driver_count": driver_count,
            "driver_source": driver_source,
            "revenue_per_truck": revenue_per_truck,
            "revenue_per_driver": revenue_per_driver,
            "truck_target_delta": _target_delta(revenue_per_truck, TARGET_REVENUE_PER_TRUCK_WEEK),
            "driver_target_delta": _target_delta(revenue_per_driver, TARGET_REVENUE_PER_DRIVER_WEEK),
            "truck_target_status": _target_status(revenue_per_truck, TARGET_REVENUE_PER_TRUCK_WEEK),
            "driver_target_status": _target_status(revenue_per_driver, TARGET_REVENUE_PER_DRIVER_WEEK),
        },
        "sources": {
            "revenue": xcelerator["sources"]["revenue"],
            "trucks": geotab["sources"]["trucks"],
            "drivers": driver_source_payload,
        },
        "xcelerator_table": xcelerator.get("table"),
    }
