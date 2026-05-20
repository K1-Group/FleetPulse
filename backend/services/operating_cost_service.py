"""Read-only operating cost rollups for FleetPulse.

This service joins cost evidence without changing any source system:

- Geotab Data Connector owns miles and hours.
- AtoB exports provide fuel-card audit evidence.
- Xcelerator ReviewOrders owns driver pay.
- QuickBooks Online K1 Logistics owns maintenance, fuel, insurance,
  employee, rental truck, and trailer operating expenses.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from integrations.fabric_warehouse.sql_client import (
    FabricWarehouseSqlConfig,
    execute_sql_query,
)
from services.atob_fuel_expense_service import AtoBFuelExpenseStateStore
from services.lane_stability_service import (
    LaneStabilityConfig,
    get_lane_stability_snapshot,
)
from services.qbo_financial_snapshot_service import QBO_K1L_COST_BUCKETS, load_qbo_k1l_expense_rows
from services.xcelerator_review_orders_import_service import (
    XceleratorReviewOrdersStateTooLarge,
    get_xcelerator_review_orders_weekly_driver_pay,
)


GEOTAB_AUTHORITY = "K1 Logistics Inc / Geotab Data Connector"
GEOTAB_FABRIC_AUTHORITY = "K1 Logistics Inc / Geotab telemetry Fabric Warehouse projection"
ATOB_AUTHORITY = "AtoB manual fuel expense export"
XCELERATOR_AUTHORITY = "K1 Group LLC / Xcelerator"
XCELERATOR_FABRIC_AUTHORITY = "K1 Group LLC / Xcelerator Fabric Warehouse SQL"
QBO_AUTHORITY = "K1 Logistics Inc / QuickBooks Online"
OPERATING_COST_AUTHORITY = (
    "Geotab miles/hours + Xcelerator sales/driver pay + QBO K1 Logistics cost stack"
)
K1L_INSURANCE_RATE_AUTHORITY = "K1 Logistics Inc insurance allocation"
DEFAULT_K1L_INSURANCE_COST_PER_MILE = 0.27
KM_TO_MILES = 0.621371
_EMPLOYEE_PATTERNS = (
    "employee",
    "company contributions",
    "health insurance",
    "payroll",
    "pre-employment",
    "salary",
    "salaries",
    "wages",
    "worker",
)
_RENTAL_TRUCK_TRAILER_PATTERNS = (
    "bruckner",
    "camarena",
    "equipment rental",
    "equipment rental - cogs",
    "idlease",
    "idealease",
    "ryder",
    "truck lease",
    "trucks/trailers lease",
    "trailer lease",
    "truck rental",
    "trailer rental",
    "xtra",
    "xtra lease",
)
_MAINTENANCE_PATTERNS = (
    "2290",
    "highway used tax",
    "ifta",
    "parking",
    "permit",
    "permits",
    "repair",
    "maintenance",
    "road services",
    "safety compliance",
    "registration",
    "registrations",
    "toll",
    "tolls",
    "towing",
    "license",
    "licenses",
    "truck wash",
    "vehicle registration",
    "vehicle wash",
)
_FUEL_PATTERNS = (
    "diesel",
    "fuel",
    "fuel - cost",
    "gas & fuel",
    "vehicle gas",
    "vehicle gas & fuel",
)


@dataclass(frozen=True)
class QboExpenseFeedConfig:
    """Runtime settings for a read-only QBO expense projection."""

    url: str = ""
    path: str = ""
    api_key: str = ""
    api_key_header: str = "X-FleetPulse-QBO-Key"
    timeout_seconds: float = 30.0
    insurance_patterns: tuple[str, ...] = ("insurance",)
    insurance_cost_per_mile: float = DEFAULT_K1L_INSURANCE_COST_PER_MILE
    excluded_patterns: tuple[str, ...] = (
        "accounts payable",
        "accounts receivable",
        "brokerage commission",
        "carrier",
        "commissions & fees",
        "contractor",
        "driver pay",
        "driver settlement",
        "factoring",
        "income",
        "revenue",
        "sales",
    )

    @classmethod
    def from_env(cls) -> "QboExpenseFeedConfig":
        return cls(
            url=(
                os.getenv("FLEETPULSE_QBO_EXPENSE_FEED_URL", "").strip()
                or os.getenv("FLEETPULSE_QBO_FINANCIAL_FEED_URL", "").strip()
            ),
            path=(
                os.getenv("FLEETPULSE_QBO_EXPENSE_STATE_PATH", "").strip()
                or os.getenv("FLEETPULSE_QBO_EXPENSE_FEED_PATH", "").strip()
                or os.getenv("FLEETPULSE_QBO_FINANCIAL_FEED_PATH", "").strip()
            ),
            api_key=(
                os.getenv("FLEETPULSE_QBO_EXPENSE_FEED_API_KEY", "").strip()
                or os.getenv("FLEETPULSE_QBO_FINANCIAL_FEED_API_KEY", "").strip()
            ),
            api_key_header=(
                os.getenv(
                    "FLEETPULSE_QBO_EXPENSE_FEED_API_KEY_HEADER",
                    os.getenv("FLEETPULSE_QBO_FINANCIAL_FEED_API_KEY_HEADER", "X-FleetPulse-QBO-Key"),
                ).strip()
                or "X-FleetPulse-QBO-Key"
            ),
            timeout_seconds=_float_env("FLEETPULSE_QBO_EXPENSE_TIMEOUT_SECONDS", 30.0),
            insurance_patterns=_csv_env(
                "FLEETPULSE_QBO_INSURANCE_ACCOUNT_PATTERNS",
                "insurance",
            ),
            insurance_cost_per_mile=_float_env(
                "FLEETPULSE_K1L_INSURANCE_COST_PER_MILE",
                DEFAULT_K1L_INSURANCE_COST_PER_MILE,
            ),
            excluded_patterns=_csv_env(
                "FLEETPULSE_QBO_EXCLUDED_ACCOUNT_PATTERNS",
                (
                    "accounts payable,accounts receivable,brokerage commission,"
                    "carrier,commissions & fees,driver pay,driver settlement,contractor,"
                    "factoring,income,revenue,sales"
                ),
            ),
        )

    @property
    def configured(self) -> bool:
        return bool(self.url or self.path)


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _coerce_date(value: date | datetime | str | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.split()[0], fmt).date()
        except ValueError:
            continue
    return None


def _resolve_window(
    days: int,
    start: date | datetime | str | None,
    end: date | datetime | str | None,
) -> tuple[date, date]:
    window_end = _coerce_date(end) or _today()
    window_start = _coerce_date(start)
    if window_start is None:
        safe_days = min(max(int(days or 90), 1), 370)
        window_start = window_end - timedelta(days=safe_days - 1)
    if window_start > window_end:
        raise ValueError("start must be on or before end")
    return window_start, window_end


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _week_windows(start: date, end: date) -> list[tuple[date, date]]:
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        week_end = min(_week_start(cursor) + timedelta(days=6), end)
        windows.append((cursor, week_end))
        cursor = week_end + timedelta(days=1)
    return windows


def _week_key(day: date) -> str:
    return _week_start(day).isoformat()


def _source(status: str, authority: str, *, message: str = "", row_count: int = 0) -> dict[str, Any]:
    return {
        "status": status,
        "source_authority": authority,
        "projection_mode": "read_only",
        "message": message,
        "row_count": row_count,
    }


def _quote_sql_identifier(value: Any) -> str:
    return f"[{str(value or '').replace(']', ']]')}]"


def _quote_sql_literal(value: Any) -> str:
    return f"'{str(value or '').replace(chr(39), chr(39) + chr(39))}'"


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    negative = text.startswith("(") and text.endswith(")")
    cleaned = text.replace("$", "").replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return 0.0
    number = float(match.group(0))
    return -abs(number) if negative else number


def _find_value(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    normalized = {_normalize(alias) for alias in aliases}
    for key, value in row.items():
        if _normalize(key) in normalized:
            return value
    return None


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _money(value: float) -> float:
    return round(float(value or 0), 2)


def _empty_week(start: date, end: date) -> dict[str, Any]:
    week = _week_start(start)
    return {
        "week_start": week.isoformat(),
        "week_end": end.isoformat(),
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "miles": 0.0,
        "drive_hours": 0.0,
        "idle_hours": 0.0,
        "operating_hours": 0.0,
        "trips": 0,
        "fuel_cost": 0.0,
        "fuel_card_audit_cost": 0.0,
        "driver_pay": 0.0,
        "maintenance_cost": 0.0,
        "insurance_cost": 0.0,
        "posted_insurance_cost": 0.0,
        "insurance_cost_method": "per_mile_rate",
        "insurance_cost_per_mile": DEFAULT_K1L_INSURANCE_COST_PER_MILE,
        "employee_cost": 0.0,
        "rental_trucks_trailers_cost": 0.0,
        "other_expense_cost": 0.0,
        "known_operating_cost": 0.0,
        "true_operating_cost": None,
        "known_cost_per_mile": None,
        "true_cost_per_mile": None,
        "known_cost_per_drive_hour": None,
        "true_cost_per_drive_hour": None,
        "known_cost_per_operating_hour": None,
        "true_cost_per_operating_hour": None,
    }


def _geotab_warehouse_config_from_env() -> FabricWarehouseSqlConfig:
    config = FabricWarehouseSqlConfig.from_env("FLEETPULSE_GEOTAB_WAREHOUSE_SQL")
    if config.configured:
        return config
    return FabricWarehouseSqlConfig.from_env("FLEETPULSE_XCELERATOR_WAREHOUSE_SQL")


def _build_geotab_warehouse_table_discovery_sql() -> str:
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


def _build_xcelerator_review_orders_table_discovery_sql() -> str:
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
        LOWER(objects.name) = 'xcelerator_review_orders'
        OR LOWER(objects.name) LIKE '%xcelerator%review%orders%'
    )
ORDER BY
    CASE WHEN LOWER(objects.name) = 'xcelerator_review_orders' THEN 0 ELSE 1 END,
    schemas.name,
    objects.name
""".strip()


def _build_table_columns_sql(table_schema: str, table_name: str) -> str:
    return f"""
SELECT columns.name AS column_name
FROM sys.columns AS columns
JOIN sys.objects AS objects
    ON objects.object_id = columns.object_id
JOIN sys.schemas AS schemas
    ON schemas.schema_id = objects.schema_id
WHERE schemas.name = {_quote_sql_literal(table_schema)}
    AND objects.name = {_quote_sql_literal(table_name)}
ORDER BY columns.column_id
""".strip()


def _column_by_alias(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    normalized_aliases = {_normalize(alias) for alias in aliases}
    for column in columns:
        normalized_column = _normalize(column)
        if normalized_column in normalized_aliases:
            return column
    for column in columns:
        normalized_column = _normalize(column)
        if any(normalized_column.endswith(alias) for alias in normalized_aliases):
            return column
    return None


def _decimal_expr(column: str | None, divisor: float = 1.0) -> str:
    if not column:
        return "0"
    expression = f"COALESCE(TRY_CONVERT(float, {_quote_sql_identifier(column)}), 0)"
    if divisor != 1.0:
        return f"({expression} / {divisor})"
    return expression


def _build_geotab_warehouse_weekly_sql(
    start: date,
    end: date,
    *,
    table_schema: str,
    table_name: str,
    columns: list[str],
) -> str | None:
    date_column = _column_by_alias(
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
    if not date_column:
        return None

    distance_km_column = _column_by_alias(
        columns,
        (
            "Distance_Km",
            "GPS_Distance_Km",
            "TotalDistance_Km",
            "DistanceKm",
            "Distance KM",
        ),
    )
    distance_miles_column = _column_by_alias(
        columns,
        (
            "Distance_Miles",
            "DistanceMiles",
            "TotalDistance_Miles",
            "Total Miles",
            "Miles",
        ),
    )
    drive_seconds_column = _column_by_alias(
        columns,
        ("DriveDuration_Seconds", "Drive Duration Seconds", "DrivingDurationSeconds"),
    )
    drive_hours_column = _column_by_alias(
        columns,
        (
            "TotalDriveTime_Hours",
            "DriveTime_Hours",
            "Drive Hours",
            "Driving Hours",
            "Total Driving Hours",
        ),
    )
    idle_seconds_column = _column_by_alias(
        columns,
        ("IdleDuration_Seconds", "Idle Duration Seconds", "IdlingDurationSeconds"),
    )
    idle_hours_column = _column_by_alias(
        columns,
        (
            "TotalIdleTime_Hours",
            "IdleTime_Hours",
            "Idle Hours",
            "Idling Hours",
            "Total Idling Hours",
        ),
    )
    trips_column = _column_by_alias(columns, ("Trip_Count", "TotalTrips", "Trips", "Trip Count"))

    date_expr = f"TRY_CONVERT(date, {_quote_sql_identifier(date_column)})"
    table_ref = f"{_quote_sql_identifier(table_schema)}.{_quote_sql_identifier(table_name)}"
    miles_expr = " + ".join(
        part
        for part in (
            f"({_decimal_expr(distance_km_column)} * {KM_TO_MILES})" if distance_km_column else "",
            _decimal_expr(distance_miles_column) if distance_miles_column else "",
        )
        if part
    ) or "0"
    drive_hours_expr = " + ".join(
        part
        for part in (
            _decimal_expr(drive_seconds_column, 3600) if drive_seconds_column else "",
            _decimal_expr(drive_hours_column) if drive_hours_column else "",
        )
        if part
    ) or "0"
    idle_hours_expr = " + ".join(
        part
        for part in (
            _decimal_expr(idle_seconds_column, 3600) if idle_seconds_column else "",
            _decimal_expr(idle_hours_column) if idle_hours_column else "",
        )
        if part
    ) or "0"
    trips_expr = _decimal_expr(trips_column) if trips_column else "0"

    return f"""
WITH normalized AS (
    SELECT
        {date_expr} AS activity_date,
        {miles_expr} AS miles,
        {drive_hours_expr} AS drive_hours,
        {idle_hours_expr} AS idle_hours,
        {trips_expr} AS trips
    FROM {table_ref}
    WHERE {date_expr} >= '{start.isoformat()}'
        AND {date_expr} <= '{end.isoformat()}'
)
SELECT
    CAST(DATEADD(day, -(DATEDIFF(day, 0, activity_date) % 7), activity_date) AS date) AS week_start,
    SUM(miles) AS miles,
    SUM(drive_hours) AS drive_hours,
    SUM(idle_hours) AS idle_hours,
    SUM(trips) AS trips,
    COUNT(*) AS source_rows
FROM normalized
WHERE activity_date IS NOT NULL
GROUP BY CAST(DATEADD(day, -(DATEDIFF(day, 0, activity_date) % 7), activity_date) AS date)
ORDER BY week_start
""".strip()


def _build_xcelerator_driver_pay_warehouse_weekly_sql(
    start: date,
    end: date,
    *,
    table_schema: str,
    table_name: str,
    date_column: str,
    driver_pay_column: str,
    delivery_center_column: str | None,
) -> str:
    table_ref = f"{_quote_sql_identifier(table_schema)}.{_quote_sql_identifier(table_name)}"
    date_expr = f"TRY_CONVERT(date, {_quote_sql_identifier(date_column)})"
    driver_pay_expr = f"COALESCE(TRY_CONVERT(decimal(18, 2), {_quote_sql_identifier(driver_pay_column)}), 0)"
    delivery_center_expr = (
        f"CONVERT(nvarchar(255), {_quote_sql_identifier(delivery_center_column)})"
        if delivery_center_column
        else "''"
    )
    delivery_center_filter = (
        "AND LOWER(delivery_center) LIKE '%k1 logistics%'"
        if delivery_center_column
        else ""
    )
    return f"""
WITH normalized AS (
    SELECT
        {date_expr} AS row_day,
        {driver_pay_expr} AS driver_pay,
        {delivery_center_expr} AS delivery_center
    FROM {table_ref}
    WHERE {date_expr} >= {_quote_sql_literal(start.isoformat())}
        AND {date_expr} <= {_quote_sql_literal(end.isoformat())}
),
filtered AS (
    SELECT
        row_day,
        driver_pay,
        DATEADD(day, -(DATEDIFF(day, CONVERT(date, '19000101'), row_day) % 7), row_day) AS week_start
    FROM normalized
    WHERE row_day IS NOT NULL
        AND driver_pay <> 0
        {delivery_center_filter}
)
SELECT
    CONVERT(varchar(10), week_start, 23) AS week_start,
    CONVERT(float, SUM(driver_pay)) AS driver_pay,
    COUNT(1) AS row_count,
    MIN(row_day) AS date_min,
    MAX(row_day) AS date_max
FROM filtered
GROUP BY week_start
ORDER BY week_start
""".strip()


def _warehouse_geotab_weekly_metrics(
    weeks: list[tuple[date, date]],
    *,
    config: FabricWarehouseSqlConfig,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if not config.configured:
        return {}, _source(
            "not_configured",
            GEOTAB_FABRIC_AUTHORITY,
            message="Fabric Warehouse SQL auth is not configured for Geotab telemetry.",
        )

    period_start = weeks[0][0]
    period_end = weeks[-1][1]
    table_rows = execute_sql_query(config, _build_geotab_warehouse_table_discovery_sql())
    if not table_rows:
        return {}, _source(
            "awaiting_feed",
            GEOTAB_FABRIC_AUTHORITY,
            message="Fabric Warehouse connected, but no Geotab daily telemetry table was visible.",
        )

    table_schema = str(_find_value(table_rows[0], ("table_schema", "TABLE_SCHEMA")) or "dbo")
    table_name = str(_find_value(table_rows[0], ("table_name", "TABLE_NAME")) or "ntta_geotab_daily_report")
    column_rows = execute_sql_query(config, _build_table_columns_sql(table_schema, table_name))
    columns = [
        str(_find_value(row, ("column_name", "COLUMN_NAME")) or "").strip()
        for row in column_rows
        if str(_find_value(row, ("column_name", "COLUMN_NAME")) or "").strip()
    ]
    weekly_sql = _build_geotab_warehouse_weekly_sql(
        period_start,
        period_end,
        table_schema=table_schema,
        table_name=table_name,
        columns=columns,
    )
    source = _source("healthy", GEOTAB_FABRIC_AUTHORITY)
    source["table"] = f"{table_schema}.{table_name}"
    source["path"] = "fabric_warehouse_sql"
    if not weekly_sql:
        return {}, {
            **source,
            "status": "awaiting_feed",
            "message": "Geotab telemetry table is visible, but no supported date column was found.",
        }

    rows = execute_sql_query(config, weekly_sql)
    metrics: dict[str, dict[str, Any]] = {}
    row_count = 0
    for row in rows:
        week = _coerce_date(_find_value(row, ("week_start", "WeekStart")))
        if week is None:
            continue
        bucket = _empty_week(week, min(week + timedelta(days=6), period_end))
        bucket["miles"] = round(_number(_find_value(row, ("miles", "Miles"))), 2)
        bucket["drive_hours"] = round(_number(_find_value(row, ("drive_hours", "DriveHours"))), 2)
        bucket["idle_hours"] = round(_number(_find_value(row, ("idle_hours", "IdleHours"))), 2)
        bucket["operating_hours"] = round(bucket["drive_hours"] + bucket["idle_hours"], 2)
        bucket["trips"] = int(_number(_find_value(row, ("trips", "Trips"))))
        metrics[_week_key(week)] = bucket
        row_count += int(_number(_find_value(row, ("source_rows", "SourceRows")))) or 1

    return metrics, {
        **source,
        "status": "healthy" if metrics else "awaiting_feed",
        "message": "" if metrics else "Fabric Warehouse returned no Geotab telemetry rows for this period.",
        "row_count": row_count,
    }


async def _fetch_vehicle_kpi_rows(start: date, end: date, *, top: int = 5000) -> list[dict[str, Any]]:
    from routers import data_connector

    return await data_connector._odata_get(  # noqa: SLF001 - shared internal OData helper.
        "VehicleKpi_Daily",
        search=f"from_{start.isoformat()}_to_{end.isoformat()}",
        top=top,
    )


def _vehicle_kpi_day(row: dict[str, Any]) -> date | None:
    return _coerce_date(
        _find_value(
            row,
            (
                "Date",
                "date",
                "Day",
                "day",
                "ReportDate",
                "Report Date",
                "LocalDate",
                "Local Date",
                "ActivityDate",
                "Activity Date",
                "CalendarDate",
                "Calendar Date",
            ),
        )
    )


def _accumulate_vehicle_kpi_row(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    distance_km = _number(
        _find_value(row, ("Distance_Km", "GPS_Distance_Km", "TotalDistance_Km"))
    )
    drive_hours = _number(_find_value(row, ("DriveDuration_Seconds",))) / 3600
    drive_hours += _number(_find_value(row, ("TotalDriveTime_Hours",)))
    idle_hours = _number(_find_value(row, ("IdleDuration_Seconds",))) / 3600
    idle_hours += _number(_find_value(row, ("TotalIdleTime_Hours",)))
    engine_hours = _number(_find_value(row, ("TotalEngine_Hours", "Engine_Hours", "Engine Hours")))
    if drive_hours + idle_hours <= 0 and engine_hours > 0:
        drive_hours = engine_hours
    bucket["miles"] += distance_km * KM_TO_MILES
    bucket["drive_hours"] += drive_hours
    bucket["idle_hours"] += idle_hours
    bucket["trips"] += int(_number(_find_value(row, ("Trip_Count", "TotalTrips"))))


async def _geotab_weekly_metrics(
    weeks: list[tuple[date, date]],
    *,
    warehouse_config: FabricWarehouseSqlConfig | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {
        _week_key(start): _empty_week(start, end) for start, end in weeks
    }
    row_count = 0
    failures: list[str] = []
    period_start = weeks[0][0]
    period_end = weeks[-1][1]

    if os.getenv("FLEETPULSE_OPERATING_COST_GEOTAB_WAREHOUSE", "true").strip().lower() not in {"0", "false", "no"}:
        try:
            warehouse_metrics, warehouse_source = await asyncio.to_thread(
                _warehouse_geotab_weekly_metrics,
                weeks,
                config=warehouse_config or _geotab_warehouse_config_from_env(),
            )
            if warehouse_metrics:
                for key, bucket in warehouse_metrics.items():
                    metrics.setdefault(key, bucket).update(
                        {
                            "miles": bucket["miles"],
                            "drive_hours": bucket["drive_hours"],
                            "idle_hours": bucket["idle_hours"],
                            "operating_hours": bucket["operating_hours"],
                            "trips": bucket["trips"],
                        }
                    )
                return metrics, warehouse_source
        except Exception as exc:  # pragma: no cover - OData fallback keeps legacy path alive.
            failures.append(f"Fabric Warehouse Geotab telemetry: {type(exc).__name__}")

    if os.getenv("FLEETPULSE_OPERATING_COST_GEOTAB_BULK", "true").strip().lower() not in {"0", "false", "no"}:
        try:
            bulk_top = max(int(os.getenv("FLEETPULSE_OPERATING_COST_GEOTAB_BULK_TOP", "50000")), 1000)
        except ValueError:
            bulk_top = 50000
        try:
            rows = await _fetch_vehicle_kpi_rows(period_start, period_end, top=bulk_top)
            dated_rows = 0
            for row in rows:
                row_day = _vehicle_kpi_day(row)
                if row_day is None or not (period_start <= row_day <= period_end):
                    continue
                dated_rows += 1
                bucket = metrics.setdefault(_week_key(row_day), _empty_week(row_day, row_day))
                _accumulate_vehicle_kpi_row(bucket, row)
            if dated_rows:
                for bucket in metrics.values():
                    bucket["miles"] = round(bucket["miles"], 2)
                    bucket["drive_hours"] = round(bucket["drive_hours"], 2)
                    bucket["idle_hours"] = round(bucket["idle_hours"], 2)
                    bucket["operating_hours"] = round(bucket["drive_hours"] + bucket["idle_hours"], 2)
                return metrics, _source("healthy", GEOTAB_AUTHORITY, row_count=dated_rows)
        except Exception:  # pragma: no cover - fallback keeps legacy path available.
            pass

    try:
        concurrency = max(int(os.getenv("FLEETPULSE_OPERATING_COST_GEOTAB_CONCURRENCY", "4")), 1)
    except ValueError:
        concurrency = 4
    try:
        retries = max(int(os.getenv("FLEETPULSE_OPERATING_COST_GEOTAB_RETRIES", "2")), 0)
    except ValueError:
        retries = 2
    semaphore = asyncio.Semaphore(min(concurrency, 8))

    async def fetch_week(start: date, end: date) -> tuple[date, date, list[dict[str, Any]], str | None]:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                async with semaphore:
                    rows = await _fetch_vehicle_kpi_rows(start, end)
                return start, end, rows, None
            except Exception as exc:  # pragma: no cover - exact upstream exception varies.
                last_error = exc
                if attempt < retries:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
        message = type(last_error).__name__ if last_error else "unknown"
        return start, end, [], f"{start.isoformat()}..{end.isoformat()}: {message}"

    for start, end, rows, failure in await asyncio.gather(
        *(fetch_week(start, end) for start, end in weeks)
    ):
        key = _week_key(start)
        bucket = metrics.setdefault(key, _empty_week(start, end))
        if failure:
            failures.append(failure)
            continue

        row_count += len(rows)
        for row in rows:
            _accumulate_vehicle_kpi_row(bucket, row)

    for bucket in metrics.values():
        bucket["miles"] = round(bucket["miles"], 2)
        bucket["drive_hours"] = round(bucket["drive_hours"], 2)
        bucket["idle_hours"] = round(bucket["idle_hours"], 2)
        bucket["operating_hours"] = round(bucket["drive_hours"] + bucket["idle_hours"], 2)

    if row_count:
        return metrics, _source(
            "partial" if failures else "healthy",
            GEOTAB_AUTHORITY,
            message="; ".join(failures[:3]) if failures else "",
            row_count=row_count,
        )
    if failures:
        return metrics, _source(
            "unavailable",
            GEOTAB_AUTHORITY,
            message="; ".join(failures[:3]),
            row_count=0,
        )
    return metrics, _source("healthy", GEOTAB_AUTHORITY, row_count=0)


def _raw_value(record: dict[str, Any], *names: str) -> Any:
    raw = record.get("raw")
    if isinstance(raw, dict):
        normalized = {_normalize(name) for name in names}
        for key, value in raw.items():
            if _normalize(key) in normalized:
                return value
    return None


def _atob_record_day(record: dict[str, Any]) -> date | None:
    return _coerce_date(record.get("transaction_date") or _raw_value(record, "Transaction Date (GMT)"))


def _atob_record_is_approved(record: dict[str, Any]) -> bool:
    status = str(_raw_value(record, "Status") or "").strip().casefold()
    return not status or status == "approved"


def _atob_record_is_fuel_related(record: dict[str, Any]) -> bool:
    gallons = _number(record.get("gallons") or _raw_value(record, "Gallons"))
    if gallons > 0:
        return True
    fuel_type = str(_raw_value(record, "Type") or "").casefold()
    return any(token in fuel_type for token in ("diesel", "fuel", "reefer", "unleaded"))


def _atob_record_cost(record: dict[str, Any]) -> float:
    net = _raw_value(record, "Net of Discount", "Net")
    if net not in (None, ""):
        return _number(net)
    return _number(record.get("amount_usd"))


def _atob_weekly_costs(
    start: date,
    end: date,
    *,
    store: AtoBFuelExpenseStateStore | None = None,
) -> tuple[dict[str, float], dict[str, Any]]:
    records = (store or AtoBFuelExpenseStateStore()).records()
    weekly: dict[str, float] = {}
    row_count = 0
    for record in records:
        day = _atob_record_day(record)
        if day is None or not (start <= day <= end):
            continue
        if not _atob_record_is_approved(record) or not _atob_record_is_fuel_related(record):
            continue
        weekly[_week_key(day)] = weekly.get(_week_key(day), 0.0) + _atob_record_cost(record)
        row_count += 1

    status = "healthy" if row_count else "awaiting_feed"
    message = "" if row_count else "No approved AtoB fuel/DEF rows are imported for this period."
    return {key: _money(value) for key, value in weekly.items()}, _source(
        status,
        ATOB_AUTHORITY,
        message=message,
        row_count=row_count,
    )


def _xcelerator_warehouse_driver_pay_by_week(
    start: date,
    end: date,
) -> tuple[dict[str, float], dict[str, Any]]:
    config = FabricWarehouseSqlConfig.from_env("FLEETPULSE_XCELERATOR_WAREHOUSE_SQL")
    if not config.configured:
        return {}, _source(
            "not_configured",
            XCELERATOR_FABRIC_AUTHORITY,
            message="Fabric Warehouse SQL auth is not configured for Xcelerator driver pay.",
        )

    try:
        table_rows = execute_sql_query(config, _build_xcelerator_review_orders_table_discovery_sql())
        if not table_rows:
            return {}, _source(
                "awaiting_feed",
                XCELERATOR_FABRIC_AUTHORITY,
                message="No visible Xcelerator ReviewOrders table was found in Fabric Warehouse SQL.",
            )

        table_schema = str(table_rows[0].get("table_schema") or "dbo")
        table_name = str(table_rows[0].get("table_name") or "xcelerator_review_orders")
        column_rows = execute_sql_query(config, _build_table_columns_sql(table_schema, table_name))
        columns = [str(row.get("column_name") or "") for row in column_rows if row.get("column_name")]
        date_column = _column_by_alias(
            columns,
            (
                "pickup_target_from",
                "[P]From Date",
                "PFrom Date",
                "From Date",
                "Order Date",
                "date",
            ),
        )
        driver_pay_column = _column_by_alias(
            columns,
            ("driver_pay_amount", "Driver Pay", "DriverPay", "driver_pay"),
        )
        delivery_center_column = _column_by_alias(
            columns,
            ("delivery_center", "Delivery Center", "DeliveryCenter", "Delivery Center Name"),
        )
        if not date_column or not driver_pay_column:
            return {}, _source(
                "unavailable",
                XCELERATOR_FABRIC_AUTHORITY,
                message="Xcelerator ReviewOrders is missing date or driver-pay columns.",
            )

        rows = execute_sql_query(
            config,
            _build_xcelerator_driver_pay_warehouse_weekly_sql(
                start,
                end,
                table_schema=table_schema,
                table_name=table_name,
                date_column=date_column,
                driver_pay_column=driver_pay_column,
                delivery_center_column=delivery_center_column,
            ),
        )
    except Exception as exc:
        return {}, _source(
            "unavailable",
            XCELERATOR_FABRIC_AUTHORITY,
            message=f"Fabric Warehouse SQL unavailable: {type(exc).__name__}: {exc}",
        )

    weekly: dict[str, float] = {}
    row_count = 0
    date_values: list[date] = []
    for row in rows:
        week = str(row.get("week_start") or "").strip()
        if not week:
            continue
        weekly[week] = _money(_number(row.get("driver_pay")))
        row_count += int(_number(row.get("row_count")))
        for key in ("date_min", "date_max"):
            if parsed := _coerce_date(row.get(key)):
                date_values.append(parsed)

    source = _source(
        "healthy" if row_count else "awaiting_feed",
        XCELERATOR_FABRIC_AUTHORITY,
        message="" if row_count else "Fabric Warehouse SQL returned no K1L driver-pay rows for this period.",
        row_count=row_count,
    )
    source["path"] = "fabric_warehouse_sql"
    source["table"] = f"{table_schema}.{table_name}"
    if not delivery_center_column:
        source["status"] = "partial" if row_count else source["status"]
        source["message"] = (
            "Delivery-center column was unavailable, so driver pay could not be filtered to K1 Logistics Inc."
            if row_count
            else source["message"]
        )
    if row_count and date_values and (min(date_values) > start or max(date_values) < end):
        source["status"] = "partial"
        source["message"] = (
            f"Driver-pay rows cover {min(date_values).isoformat()}..{max(date_values).isoformat()}, "
            f"not the full requested {start.isoformat()}..{end.isoformat()} period."
        )
    return weekly, source


def _xcelerator_driver_pay_by_week(
    start: date,
    end: date,
    *,
    config: LaneStabilityConfig | None = None,
) -> tuple[dict[str, float], dict[str, Any]]:
    warehouse_weekly, warehouse_source = _xcelerator_warehouse_driver_pay_by_week(start, end)
    if warehouse_source.get("status") == "healthy":
        return warehouse_weekly, warehouse_source

    if os.getenv("FLEETPULSE_XCELERATOR_REVIEW_ORDERS_STATE_PATH", "").strip():
        try:
            imported = get_xcelerator_review_orders_weekly_driver_pay(start, end)
        except XceleratorReviewOrdersStateTooLarge:
            return warehouse_weekly, warehouse_source
        except Exception as exc:
            if warehouse_source.get("status") != "not_configured":
                return warehouse_weekly, warehouse_source
            return {}, _source(
                "unavailable",
                XCELERATOR_AUTHORITY,
                message=f"{type(exc).__name__}: {exc}",
            )
        row_count = int(imported.get("row_count") or 0)
        if not row_count:
            return {}, _source(
                "awaiting_feed",
                XCELERATOR_AUTHORITY,
                message="Xcelerator ReviewOrders rows are not imported for this period.",
            )
        source_status = "healthy"
        source_message = ""
        date_min = _coerce_date(imported.get("date_min"))
        date_max = _coerce_date(imported.get("date_max"))
        if not date_min or not date_max or date_min > start or date_max < end:
            source_status = "partial"
            source_message = (
                f"Driver-pay rows cover {imported.get('date_min')}..{imported.get('date_max')}, "
                f"not the full requested {start.isoformat()}..{end.isoformat()} period."
            )
        return dict(imported.get("weekly") or {}), _source(
            source_status,
            XCELERATOR_AUTHORITY,
            message=source_message,
            row_count=row_count,
        )

    if warehouse_source.get("status") != "not_configured":
        return warehouse_weekly, warehouse_source

    config = config or LaneStabilityConfig.from_env()
    if not config.configured:
        return {}, _source(
            "awaiting_feed",
            XCELERATOR_AUTHORITY,
            message="Xcelerator ReviewOrders driver-pay feed is not configured.",
        )

    snapshot = get_lane_stability_snapshot(
        days=(end - start).days + 1,
        start=start,
        end=end,
        config=config,
    )
    status = str(snapshot.get("feed_status") or "unavailable")
    if status != "healthy":
        return {}, _source(
            status,
            XCELERATOR_AUTHORITY,
            message=str(snapshot.get("company_kpis", {}).get("feed_message") or ""),
        )

    weekly: dict[str, float] = {}
    date_rows: list[date] = []
    row_count = 0
    for row in snapshot.get("daily") or []:
        day = _coerce_date(row.get("date"))
        if day is None or not (start <= day <= end):
            continue
        date_rows.append(day)
        weekly[_week_key(day)] = weekly.get(_week_key(day), 0.0) + _number(row.get("driver_pay"))
        row_count += 1
    if not row_count:
        return {}, _source(
            "awaiting_feed",
            XCELERATOR_AUTHORITY,
            message="Xcelerator ReviewOrders feed is configured, but no driver-pay rows are available for this period.",
        )
    source_status = "healthy"
    source_message = ""
    if min(date_rows) > start or max(date_rows) < end:
        source_status = "partial"
        source_message = (
            f"Driver-pay rows cover {min(date_rows).isoformat()}..{max(date_rows).isoformat()}, "
            f"not the full requested {start.isoformat()}..{end.isoformat()} period."
        )
    return {key: _money(value) for key, value in weekly.items()}, _source(
        source_status,
        XCELERATOR_AUTHORITY,
        message=source_message,
        row_count=row_count,
    )


def _load_qbo_feed(config: QboExpenseFeedConfig) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if config.url:
        headers = {"Accept": "application/json,text/csv"}
        if config.api_key:
            headers[config.api_key_header] = config.api_key
        with httpx.Client(timeout=config.timeout_seconds) as client:
            response = client.get(config.url, headers=headers)
        response.raise_for_status()
        return _coerce_feed(response.text, response.headers.get("content-type", ""))
    if config.path:
        path = Path(config.path)
        if not path.exists():
            return [], {}
        return _coerce_feed(path.read_text(encoding="utf-8-sig"), "")
    return [], {}


def _coerce_feed(text: str, content_type: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stripped = text.lstrip("\ufeff").strip()
    if not stripped:
        return [], {}
    if "json" in content_type or stripped[:1] in {"[", "{"}:
        payload = json.loads(stripped)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)], {}
        if isinstance(payload, dict):
            metadata = {
                key: payload.get(key)
                for key in ("coverage_start", "coverage_end", "last_imported_at")
                if payload.get(key)
            }
            for key in (
                "expense_rows",
                "k1l_expenses",
                "k1l_expense_rows",
                "expenses",
                "rows",
                "value",
                "data",
                "items",
            ):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)], metadata
            return [payload], metadata
    sample = stripped[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in sample else csv.excel
    return (
        [
            dict(row)
            for row in csv.DictReader(io.StringIO(stripped), dialect=dialect)
            if any(str(value or "").strip() for value in row.values())
        ],
        {},
    )


def _qbo_row_day(row: dict[str, Any]) -> date | None:
    return _coerce_date(
        _find_value(
            row,
            (
                "Date",
                "TxnDate",
                "Transaction Date",
                "Posted Date",
                "Accounting Date",
                "transaction_date",
            ),
        )
    )


def _qbo_row_amount(row: dict[str, Any]) -> float:
    amount = _find_value(
        row,
        (
            "Amount",
            "Net Amount",
            "LineAmount",
            "Expense Amount",
            "Debit",
            "Total",
            "amount_usd",
        ),
    )
    return abs(_number(amount))


def _qbo_row_bucket(row: dict[str, Any], config: QboExpenseFeedConfig) -> str | None:
    haystack = " ".join(
        str(_find_value(row, (alias,)) or "")
        for alias in (
            "Account",
            "Account Name",
            "account_name",
            "Category",
            "Expense Category",
            "category",
            "Name",
            "Vendor",
            "vendor_name",
            "entity_name",
            "Memo",
            "memo",
            "Description",
            "description",
            "Transaction Type",
            "transaction_type",
        )
    ).casefold()
    if not haystack:
        haystack = " ".join(str(value or "") for value in row.values()).casefold()
    if any(pattern.casefold() in haystack for pattern in config.excluded_patterns):
        return None
    if any(pattern in haystack for pattern in _EMPLOYEE_PATTERNS):
        return "employee"
    if any(pattern in haystack for pattern in _RENTAL_TRUCK_TRAILER_PATTERNS):
        return "rental_trucks_trailers"
    if any(pattern in haystack for pattern in _MAINTENANCE_PATTERNS):
        return "maintenance"
    if any(pattern in haystack for pattern in _FUEL_PATTERNS):
        return "fuel"
    if any(pattern.casefold() in haystack for pattern in config.insurance_patterns):
        return "insurance"
    return None


def _qbo_weekly_costs(
    start: date,
    end: date,
    *,
    config: QboExpenseFeedConfig | None = None,
) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    config = config or QboExpenseFeedConfig.from_env()
    if not config.configured:
        rows, metadata = load_qbo_k1l_expense_rows(start=start, end=end)
        if not rows:
            return {}, _source(
                "awaiting_feed",
                QBO_AUTHORITY,
                message="QBO expense feed URL/path is not configured.",
            )
    else:
        rows, metadata = _load_qbo_feed(config)
    source_authority = metadata.get("source_authority") or QBO_AUTHORITY
    if not rows:
        return {}, _source(
            "awaiting_feed",
            source_authority,
            message="QBO expense feed is configured, but no expense rows are available yet.",
        )

    weekly: dict[str, dict[str, float]] = {}
    source_row_count = 0
    included_row_count = 0
    bucket_template = {bucket: 0.0 for bucket in QBO_K1L_COST_BUCKETS}
    for row in rows:
        day = _qbo_row_day(row)
        if day is None or not (start <= day <= end):
            continue
        source_row_count += 1
        bucket_name = _qbo_row_bucket(row, config)
        if bucket_name is None:
            continue
        week = weekly.setdefault(_week_key(day), dict(bucket_template))
        week[bucket_name] += _qbo_row_amount(row)
        included_row_count += 1

    if not source_row_count:
        return {}, _source(
            "awaiting_feed",
            source_authority,
            message="QBO expense feed has no rows inside the requested reporting period.",
        )

    source_status = "healthy"
    source_message = ""
    coverage_start = _coerce_date(metadata.get("coverage_start"))
    coverage_end = _coerce_date(metadata.get("coverage_end"))
    if coverage_start and coverage_end and (coverage_start > start or coverage_end < end):
        source_status = "partial"
        source_message = (
            f"QBO expense rows are declared for {coverage_start.isoformat()}..{coverage_end.isoformat()}, "
            f"not the full requested {start.isoformat()}..{end.isoformat()} period."
        )

    return (
        {
            key: {bucket: _money(value.get(bucket, 0.0)) for bucket in QBO_K1L_COST_BUCKETS}
            for key, value in weekly.items()
        },
        _source(
            source_status,
            source_authority,
            message=source_message
            or (
                f"{included_row_count} QBO expense rows included after account exclusions."
                if included_row_count != source_row_count
                else ""
            ),
            row_count=source_row_count,
        ),
    )


def _insurance_source(config: QboExpenseFeedConfig) -> dict[str, Any]:
    rate = max(float(config.insurance_cost_per_mile or 0.0), 0.0)
    if rate > 0:
        return _source(
            "healthy",
            K1L_INSURANCE_RATE_AUTHORITY,
            message=f"K1L insurance allocated at ${rate:.2f}/mile.",
        )
    return _source(
        "disabled",
        K1L_INSURANCE_RATE_AUTHORITY,
        message="K1L insurance per-mile allocation is disabled; using posted QBO insurance rows only.",
    )


def _apply_insurance_allocation(
    weekly: dict[str, dict[str, Any]],
    *,
    config: QboExpenseFeedConfig,
) -> None:
    rate = max(float(config.insurance_cost_per_mile or 0.0), 0.0)
    for row in weekly.values():
        row["insurance_cost_per_mile"] = rate
        posted = _money(float(row.get("posted_insurance_cost") or row.get("insurance_cost") or 0.0))
        row["posted_insurance_cost"] = posted
        miles = float(row.get("miles") or 0.0)
        if rate > 0 and miles > 0:
            row["insurance_cost"] = _money(miles * rate)
            row["insurance_cost_method"] = "per_mile_rate"
            continue
        row["insurance_cost"] = posted
        row["insurance_cost_method"] = "qbo_posted" if posted else "none"


def _component_sources_complete(sources: dict[str, dict[str, Any]]) -> bool:
    return all(
        sources[name]["status"] == "healthy"
        for name in ("telemetry", "driver_pay", "qbo_expenses")
    )


def _finalize_week(row: dict[str, Any], *, complete: bool) -> dict[str, Any]:
    qbo_non_fuel_expense = (
        float(row["maintenance_cost"])
        + float(row["employee_cost"])
        + float(row["rental_trucks_trailers_cost"])
    )
    row["other_expense_cost"] = _money(qbo_non_fuel_expense)
    known_cost = (
        float(row["fuel_cost"])
        + float(row["driver_pay"])
        + float(row["insurance_cost"])
        + qbo_non_fuel_expense
    )
    row["known_operating_cost"] = _money(known_cost)
    row["known_cost_per_mile"] = _ratio(known_cost, float(row["miles"]))
    row["known_cost_per_drive_hour"] = _ratio(known_cost, float(row["drive_hours"]))
    row["known_cost_per_operating_hour"] = _ratio(known_cost, float(row["operating_hours"]))
    if complete:
        row["true_operating_cost"] = row["known_operating_cost"]
        row["true_cost_per_mile"] = row["known_cost_per_mile"]
        row["true_cost_per_drive_hour"] = row["known_cost_per_drive_hour"]
        row["true_cost_per_operating_hour"] = row["known_cost_per_operating_hour"]
    return row


def _summary_from_weekly(weekly: list[dict[str, Any]], *, complete: bool) -> dict[str, Any]:
    totals = {
        "miles": sum(float(row["miles"]) for row in weekly),
        "drive_hours": sum(float(row["drive_hours"]) for row in weekly),
        "idle_hours": sum(float(row["idle_hours"]) for row in weekly),
        "operating_hours": sum(float(row["operating_hours"]) for row in weekly),
        "trips": sum(int(row["trips"]) for row in weekly),
        "fuel_cost": sum(float(row["fuel_cost"]) for row in weekly),
        "fuel_card_audit_cost": sum(float(row.get("fuel_card_audit_cost") or 0) for row in weekly),
        "driver_pay": sum(float(row["driver_pay"]) for row in weekly),
        "maintenance_cost": sum(float(row.get("maintenance_cost") or 0) for row in weekly),
        "insurance_cost": sum(float(row["insurance_cost"]) for row in weekly),
        "posted_insurance_cost": sum(float(row.get("posted_insurance_cost") or 0) for row in weekly),
        "employee_cost": sum(float(row.get("employee_cost") or 0) for row in weekly),
        "rental_trucks_trailers_cost": sum(float(row.get("rental_trucks_trailers_cost") or 0) for row in weekly),
        "other_expense_cost": sum(float(row["other_expense_cost"]) for row in weekly),
        "known_operating_cost": sum(float(row["known_operating_cost"]) for row in weekly),
    }
    summary = {
        "miles": round(totals["miles"], 2),
        "drive_hours": round(totals["drive_hours"], 2),
        "idle_hours": round(totals["idle_hours"], 2),
        "operating_hours": round(totals["operating_hours"], 2),
        "trips": totals["trips"],
        "fuel_cost": _money(totals["fuel_cost"]),
        "fuel_card_audit_cost": _money(totals["fuel_card_audit_cost"]),
        "driver_pay": _money(totals["driver_pay"]),
        "maintenance_cost": _money(totals["maintenance_cost"]),
        "insurance_cost": _money(totals["insurance_cost"]),
        "posted_insurance_cost": _money(totals["posted_insurance_cost"]),
        "insurance_cost_per_mile": _ratio(totals["insurance_cost"], totals["miles"]),
        "employee_cost": _money(totals["employee_cost"]),
        "rental_trucks_trailers_cost": _money(totals["rental_trucks_trailers_cost"]),
        "other_expense_cost": _money(totals["other_expense_cost"]),
        "known_operating_cost": _money(totals["known_operating_cost"]),
        "true_operating_cost": _money(totals["known_operating_cost"]) if complete else None,
        "known_cost_per_mile": _ratio(totals["known_operating_cost"], totals["miles"]),
        "true_cost_per_mile": (
            _ratio(totals["known_operating_cost"], totals["miles"]) if complete else None
        ),
        "known_cost_per_drive_hour": _ratio(
            totals["known_operating_cost"], totals["drive_hours"]
        ),
        "true_cost_per_drive_hour": (
            _ratio(totals["known_operating_cost"], totals["drive_hours"]) if complete else None
        ),
        "known_cost_per_operating_hour": _ratio(
            totals["known_operating_cost"], totals["operating_hours"]
        ),
        "true_cost_per_operating_hour": (
            _ratio(totals["known_operating_cost"], totals["operating_hours"])
            if complete
            else None
        ),
    }
    return summary


async def get_operating_cost_snapshot(
    *,
    days: int = 90,
    start: date | datetime | str | None = None,
    end: date | datetime | str | None = None,
    atob_store: AtoBFuelExpenseStateStore | None = None,
    lane_config: LaneStabilityConfig | None = None,
    qbo_config: QboExpenseFeedConfig | None = None,
    include_driver_pay: bool = True,
) -> dict[str, Any]:
    """Return weekly operating-cost rows for dashboard and Power BI use."""

    period_start, period_end = _resolve_window(days, start, end)
    qbo_config = qbo_config or QboExpenseFeedConfig.from_env()
    weeks = _week_windows(period_start, period_end)
    weekly = {_week_key(start_date): _empty_week(start_date, end_date) for start_date, end_date in weeks}

    geotab_metrics, telemetry_source = await _geotab_weekly_metrics(weeks)
    fuel_by_week, fuel_source = _atob_weekly_costs(period_start, period_end, store=atob_store)
    if include_driver_pay:
        driver_pay_by_week, driver_source = _xcelerator_driver_pay_by_week(
            period_start,
            period_end,
            config=lane_config,
        )
    else:
        driver_pay_by_week, driver_source = {}, _source(
            "skipped",
            XCELERATOR_AUTHORITY,
            message="Skipped because caller supplies Xcelerator driver pay separately.",
        )
    try:
        qbo_by_week, qbo_source = _qbo_weekly_costs(period_start, period_end, config=qbo_config)
    except Exception as exc:
        qbo_by_week, qbo_source = {}, _source(
            "unavailable",
            QBO_AUTHORITY,
            message=f"{type(exc).__name__}: {exc}",
        )

    for key, metrics in geotab_metrics.items():
        weekly.setdefault(key, metrics).update(
            {
                "miles": metrics["miles"],
                "drive_hours": metrics["drive_hours"],
                "idle_hours": metrics["idle_hours"],
                "operating_hours": metrics["operating_hours"],
                "trips": metrics["trips"],
            }
        )
    for key, value in fuel_by_week.items():
        weekly.setdefault(key, _empty_week(date.fromisoformat(key), date.fromisoformat(key)))["fuel_card_audit_cost"] = value
    for key, value in driver_pay_by_week.items():
        weekly.setdefault(key, _empty_week(date.fromisoformat(key), date.fromisoformat(key)))["driver_pay"] = value
    for key, value in qbo_by_week.items():
        bucket = weekly.setdefault(key, _empty_week(date.fromisoformat(key), date.fromisoformat(key)))
        bucket["maintenance_cost"] = value.get("maintenance", 0.0)
        bucket["fuel_cost"] = value.get("fuel", 0.0)
        bucket["posted_insurance_cost"] = value.get("insurance", 0.0)
        bucket["employee_cost"] = value.get("employee", 0.0)
        bucket["rental_trucks_trailers_cost"] = value.get("rental_trucks_trailers", 0.0)

    _apply_insurance_allocation(weekly, config=qbo_config)

    sources = {
        "telemetry": telemetry_source,
        "fuel": qbo_source,
        "fuel_card_audit": fuel_source,
        "insurance": _insurance_source(qbo_config),
        "driver_pay": driver_source,
        "qbo_expenses": qbo_source,
    }
    complete = _component_sources_complete(sources)
    rows = [_finalize_week(row, complete=complete) for _, row in sorted(weekly.items())]

    unresolved_sources = [
        name
        for name, source in sources.items()
        if name != "fuel_card_audit" and source.get("status") != "healthy"
    ]

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_authority": OPERATING_COST_AUTHORITY,
        "projection_mode": "read_only",
        "grain": "weekly",
        "complete_cost_available": complete,
        "unresolved_sources": unresolved_sources,
        "sources": sources,
        "summary": _summary_from_weekly(rows, complete=complete),
        "weekly": rows,
        "row_counts": {"weekly": len(rows)},
    }
