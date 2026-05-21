"""Revenue productivity KPIs for the Vehicle Efficiency panel.

The metric boundaries stay read-only:

- Xcelerator Fabric Warehouse SQL supplies K1L revenue and dispatch drivers.
- Geotab supplies active truck counts from the same 7-day utilization window.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from geotab_client import GeotabClient
from configs.xcelerator_source import xcelerator_ceo_powerbi_only, xcelerator_source_label
from integrations.fabric_warehouse.sql_client import FabricWarehouseSqlConfig, execute_sql_query
from integrations.powerbi.execute_queries import PowerBIExecuteQueriesConfig, execute_dax_query
from services.entity_margin_service import K1L_ENTITY, _entity_from_delivery_center


XCELERATOR_AUTHORITY = "K1 Group LLC / Xcelerator review orders"
XCELERATOR_CEO_POWERBI_SOURCE = "xcelerator_ceo_powerbi"
GEOTAB_AUTHORITY = "K1 Logistics Inc / Geotab trips"
GEOTAB_WAREHOUSE_AUTHORITY = "K1 Logistics Inc / Geotab telemetry Fabric Warehouse projection"
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


def _geotab_warehouse_config_from_env() -> FabricWarehouseSqlConfig:
    config = FabricWarehouseSqlConfig.from_env("FLEETPULSE_GEOTAB_WAREHOUSE_SQL")
    if config.configured:
        return config
    return FabricWarehouseSqlConfig.from_env("FLEETPULSE_XCELERATOR_WAREHOUSE_SQL")


def _geotab_warehouse_table_discovery_sql() -> str:
    return """
SELECT TOP (10)
    schemas.name AS table_schema,
    objects.name AS table_name,
    objects.type_desc AS object_type
FROM sys.objects AS objects
JOIN sys.schemas AS schemas
    ON schemas.schema_id = objects.schema_id
WHERE objects.type IN ('U', 'V', 'ET')
    AND (
        LOWER(objects.name) = 'ntta_geotab_daily_report'
        OR LOWER(objects.name) LIKE '%geotab%daily%'
        OR LOWER(objects.name) LIKE '%vehicle%kpi%daily%'
    )
ORDER BY
    CASE WHEN LOWER(objects.name) = 'ntta_geotab_daily_report' THEN 0 ELSE 1 END,
    CASE WHEN LOWER(objects.name) LIKE '%geotab%daily%' THEN 0 ELSE 1 END,
    schemas.name,
    objects.name
""".strip()


def _decimal_sql(column: str) -> str:
    return f"COALESCE(TRY_CONVERT(float, {_quote_sql_identifier(column)}), 0)"


def _warehouse_geotab_active_trucks_sql(
    *,
    table_schema: str,
    table_name: str,
    date_column: str,
    vehicle_column: str,
    distance_km_column: str | None,
    distance_miles_column: str | None,
    period_start: date,
    period_end: date,
) -> str | None:
    miles_parts = []
    if distance_km_column:
        miles_parts.append(f"({_decimal_sql(distance_km_column)} * 0.621371)")
    if distance_miles_column:
        miles_parts.append(_decimal_sql(distance_miles_column))
    miles_expr = " + ".join(miles_parts)
    if not miles_expr:
        return None

    table_ref = f"{_quote_sql_identifier(table_schema)}.{_quote_sql_identifier(table_name)}"
    date_expr = f"TRY_CONVERT(date, {_quote_sql_identifier(date_column)})"
    vehicle_expr = f"NULLIF(LTRIM(RTRIM(CONVERT(nvarchar(255), {_quote_sql_identifier(vehicle_column)}))), '')"
    return f"""
WITH normalized AS (
    SELECT
        {date_expr} AS activity_date,
        {vehicle_expr} AS vehicle_key,
        {miles_expr} AS miles
    FROM {table_ref}
    WHERE {date_expr} >= '{period_start.isoformat()}'
        AND {date_expr} <= '{period_end.isoformat()}'
),
vehicle_miles AS (
    SELECT
        vehicle_key,
        SUM(miles) AS miles,
        COUNT(*) AS source_rows
    FROM normalized
    WHERE activity_date IS NOT NULL
        AND vehicle_key IS NOT NULL
    GROUP BY vehicle_key
)
SELECT
    vehicle_key,
    miles,
    source_rows
FROM vehicle_miles
WHERE miles >= 10
ORDER BY miles DESC
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
    if xcelerator_ceo_powerbi_only():
        return _load_xcelerator_productivity_from_powerbi(period_start, period_end)

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


def _build_powerbi_productivity_dax(period_start: date, period_end: date) -> str:
    return f"""
EVALUATE
VAR BaseRows =
    FILTER(
        ADDCOLUMNS(
            'xcelerator_review_orders',
            "PickupDate", DATEVALUE('xcelerator_review_orders'[pickup_target_from])
        ),
        NOT ISBLANK('xcelerator_review_orders'[pickup_target_from])
            && [PickupDate] >= DATE({period_start.year}, {period_start.month}, {period_start.day})
            && [PickupDate] <= DATE({period_end.year}, {period_end.month}, {period_end.day})
    )
RETURN
GROUPBY(
    BaseRows,
    'xcelerator_review_orders'[delivery_center],
    "Revenue", SUMX(CURRENTGROUP(), 'xcelerator_review_orders'[grand_total_amount]),
    "DriverCount", COUNTX(CURRENTGROUP(), 'xcelerator_review_orders'[driver_no]),
    "Orders", COUNTX(CURRENTGROUP(), 'xcelerator_review_orders'[order_tracking_id])
)
ORDER BY 'xcelerator_review_orders'[delivery_center]
""".strip()


def _load_xcelerator_productivity_from_powerbi(
    period_start: date,
    period_end: date,
) -> dict[str, Any]:
    config = PowerBIExecuteQueriesConfig.from_env("FLEETPULSE_XCELERATOR_CEO_POWERBI")
    authority = xcelerator_source_label()
    if not config.configured:
        source = _source(
            "not_configured",
            authority,
            message="Xcelerator CEO Dashboard Power BI auth is not configured.",
        )
        return {
            "revenue": None,
            "driver_count": None,
            "driver_source": "unavailable",
            "sources": {"revenue": source, "drivers": source},
            "table": XCELERATOR_CEO_POWERBI_SOURCE,
        }

    try:
        rows = execute_dax_query(config, _build_powerbi_productivity_dax(period_start, period_end))
    except Exception as exc:
        source = _source("unavailable", authority, message=f"{type(exc).__name__}: {exc}")
        return {
            "revenue": None,
            "driver_count": None,
            "driver_source": "unavailable",
            "sources": {"revenue": source, "drivers": source},
            "table": XCELERATOR_CEO_POWERBI_SOURCE,
        }

    revenue = 0.0
    driver_count = 0
    included_orders = 0
    for row in rows:
        if _entity_from_delivery_center(_find_value(row, ("delivery_center", "Delivery Center", "DeliveryCenter"))) != K1L_ENTITY:
            continue
        revenue += float(_find_value(row, ("Revenue", "revenue", "GrandTotal", "grand_total")) or 0)
        driver_count += int(float(_find_value(row, ("DriverCount", "driver_count", "drivers")) or 0))
        included_orders += int(float(_find_value(row, ("Orders", "orders", "OrderCount", "order_count")) or 0))

    revenue_source = _source(
        "healthy" if included_orders else "awaiting_feed",
        authority,
        message="" if included_orders else "No K1 Logistics Inc rows matched the CEO Dashboard semantic model for this period.",
        row_count=included_orders,
    )
    driver_source = _source(
        "healthy" if driver_count else "awaiting_feed",
        authority,
        message="" if driver_count else "No dispatch driver values were available from the CEO Dashboard semantic model.",
        row_count=driver_count,
    )
    return {
        "revenue": _money(revenue) if included_orders else None,
        "driver_count": driver_count or None,
        "driver_source": XCELERATOR_CEO_POWERBI_SOURCE if driver_count else "unavailable",
        "sources": {"revenue": revenue_source, "drivers": driver_source},
        "table": XCELERATOR_CEO_POWERBI_SOURCE,
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


def _load_geotab_warehouse_truck_activity(period_start: date, period_end: date) -> dict[str, Any]:
    config = _geotab_warehouse_config_from_env()
    if not config.configured:
        return {
            "truck_count": None,
            "source": _source(
                "not_configured",
                GEOTAB_WAREHOUSE_AUTHORITY,
                message="Fabric Warehouse SQL is not configured for Geotab telemetry.",
            ),
        }

    try:
        table_rows = execute_sql_query(config, _geotab_warehouse_table_discovery_sql())
        if not table_rows:
            return {
                "truck_count": None,
                "source": _source(
                    "awaiting_feed",
                    GEOTAB_WAREHOUSE_AUTHORITY,
                    message="No visible Geotab daily telemetry table was found.",
                ),
            }

        table = table_rows[0]
        table_schema = str(table.get("table_schema") or "dbo")
        table_name = str(table.get("table_name") or "ntta_geotab_daily_report")
        column_rows = execute_sql_query(config, _warehouse_columns_sql(table_schema, table_name))
        columns = [str(row.get("column_name") or "") for row in column_rows if row.get("column_name")]

        date_column = _pick_column(
            columns,
            (
                "Date",
                "ReportDate",
                "Report Date",
                "LocalDate",
                "Local Date",
                "ActivityDate",
                "Activity Date",
                "CalendarDate",
                "Calendar Date",
                "Day",
            ),
        )
        vehicle_column = _pick_column(
            columns,
            (
                "DeviceId",
                "Device ID",
                "DeviceID",
                "VehicleId",
                "Vehicle ID",
                "VehicleID",
                "VehicleName",
                "Vehicle Name",
                "DeviceName",
                "Device Name",
                "DeviceSerialNumber",
                "Device Serial Number",
                "SerialNumber",
                "Serial Number",
                "VIN",
            ),
        )
        distance_km_column = _pick_column(
            columns,
            (
                "Distance_Km",
                "GPS_Distance_Km",
                "TotalDistance_Km",
                "DistanceKm",
                "Distance KM",
            ),
        )
        distance_miles_column = _pick_column(
            columns,
            (
                "Distance_Miles",
                "DistanceMiles",
                "TotalDistance_Miles",
                "Total Miles",
                "Miles",
            ),
        )
        if not date_column or not vehicle_column:
            return {
                "truck_count": None,
                "source": _source(
                    "awaiting_feed",
                    GEOTAB_WAREHOUSE_AUTHORITY,
                    message="Geotab telemetry table is missing supported date or vehicle columns.",
                ),
            }

        sql = _warehouse_geotab_active_trucks_sql(
            table_schema=table_schema,
            table_name=table_name,
            date_column=date_column,
            vehicle_column=vehicle_column,
            distance_km_column=distance_km_column,
            distance_miles_column=distance_miles_column,
            period_start=period_start,
            period_end=period_end,
        )
        if not sql:
            return {
                "truck_count": None,
                "source": _source(
                    "awaiting_feed",
                    GEOTAB_WAREHOUSE_AUTHORITY,
                    message="Geotab telemetry table is missing supported distance columns.",
                ),
            }

        rows = execute_sql_query(config, sql)
    except Exception as exc:
        return {
            "truck_count": None,
            "source": _source(
                "unavailable",
                GEOTAB_WAREHOUSE_AUTHORITY,
                message=f"{type(exc).__name__}: {exc}",
            ),
        }

    truck_count = len(rows)
    source = _source(
        "healthy" if truck_count else "awaiting_feed",
        GEOTAB_WAREHOUSE_AUTHORITY,
        message="" if truck_count else "No Geotab warehouse trucks exceeded 10 miles in the period.",
        row_count=truck_count,
    )
    source["table"] = f"{table_schema}.{table_name}"
    source["path"] = "fabric_warehouse_sql"
    return {
        "truck_count": truck_count,
        "source": source,
    }


def _load_geotab_trip_activity(
    period_start_dt: datetime,
    period_end_dt: datetime,
    *,
    include_drivers: bool,
) -> dict[str, Any]:
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
        if include_drivers:
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


def _load_geotab_activity(
    period_start_dt: datetime,
    period_end_dt: datetime,
    *,
    include_driver_fallback: bool,
) -> dict[str, Any]:
    period_start = period_start_dt.date()
    period_end = period_end_dt.date()
    warehouse = _load_geotab_warehouse_truck_activity(period_start, period_end)
    driver_source = _source(
        "not_applicable" if not include_driver_fallback else "awaiting_feed",
        GEOTAB_AUTHORITY,
        message=(
            "Xcelerator dispatch driver count is available."
            if not include_driver_fallback
            else "Xcelerator dispatch driver count is unavailable; Geotab trip driver fallback is pending."
        ),
    )
    if warehouse.get("truck_count"):
        driver_count = None
        if include_driver_fallback:
            trip_payload = _load_geotab_trip_activity(
                period_start_dt,
                period_end_dt,
                include_drivers=True,
            )
            driver_count = trip_payload.get("driver_count")
            driver_source = trip_payload["sources"]["geotab_drivers"]
        return {
            "truck_count": warehouse["truck_count"],
            "driver_count": driver_count,
            "sources": {
                "trucks": warehouse["source"],
                "geotab_drivers": driver_source,
            },
        }

    trip_payload = _load_geotab_trip_activity(
        period_start_dt,
        period_end_dt,
        include_drivers=include_driver_fallback,
    )
    if trip_payload.get("truck_count") is not None:
        return trip_payload

    return {
        "truck_count": warehouse.get("truck_count"),
        "driver_count": None,
        "sources": {
            "trucks": warehouse["source"],
            "geotab_drivers": driver_source,
        },
    }


def get_revenue_productivity_snapshot(days: int = 7) -> dict[str, Any]:
    period_days = max(min(int(days or 7), 31), 1)
    period_end_dt = datetime.now(timezone.utc)
    period_start_dt = period_end_dt - timedelta(days=period_days)
    period_start = period_start_dt.date()
    period_end = period_end_dt.date()

    xcelerator = _load_xcelerator_productivity(period_start, period_end)
    geotab = _load_geotab_activity(
        period_start_dt,
        period_end_dt,
        include_driver_fallback=not bool(xcelerator.get("driver_count")),
    )

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
