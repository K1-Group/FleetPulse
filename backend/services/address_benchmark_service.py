"""Read-only historical pickup/delivery address benchmarks.

Xcelerator owns order lifecycle, revenue, driver pay, pickup, and delivery
timestamps. FleetPulse only projects those rows into historical benchmarks and
optionally annotates them with configured read-only voice/email evidence.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import csv
import hashlib
import io
import json
from pathlib import Path
import re
from statistics import median
from typing import Any
from urllib.parse import urlparse

from configs.address_benchmark import AddressBenchmarkConfig
from integrations.fabric_warehouse.sql_client import FabricWarehouseSqlConfig, execute_sql_query
from services.xcelerator_review_orders_import_service import (
    XceleratorReviewOrdersStateStore,
    XceleratorReviewOrdersStateTooLarge,
)


SOURCE_AUTHORITY = (
    "K1 Group LLC / Xcelerator ReviewOrders rows + configured voice/email evidence"
)
PROJECTION_MODE = "read_only"
VOICE_TYPES = {"voice", "voicerecording", "recording", "call", "phonecall", "voicemail"}
EMAIL_TYPES = {"email", "outlook", "message", "mail"}
ROUTE_SOURCE_AUTO = "auto"
ROUTE_SOURCE_FABRIC_WAREHOUSE = "fabric_warehouse_sql"
ROUTE_SOURCE_REVIEW_ORDERS_STATE = "review_orders_state"


def get_address_benchmark_dataset(
    *,
    pickup: str | None = None,
    delivery: str | None = None,
    days: int | None = None,
    config: AddressBenchmarkConfig | None = None,
    store: XceleratorReviewOrdersStateStore | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return historical pickup/delivery benchmarks from read-only evidence."""

    config = config or AddressBenchmarkConfig.from_env()
    now = _ensure_aware(now or datetime.now(timezone.utc))
    effective_config = (
        config
        if days is None
        else AddressBenchmarkConfig(
            **{**config.as_dict(), "period_days": max(int(days), 1)}
        )
    )
    period_end = now.date()
    period_start = period_end - timedelta(days=effective_config.period_days - 1)
    route_rows, route_meta = _load_xcelerator_route_rows(
        config=effective_config,
        period_start=period_start,
        period_end=period_end,
        store=store,
    )
    evidence_rows, evidence_meta = _load_evidence_rows(effective_config)

    return build_address_benchmark_dataset(
        route_rows,
        evidence_rows=evidence_rows,
        config=effective_config,
        pickup=pickup,
        delivery=delivery,
        now=now,
        source_meta={
            "xcelerator": route_meta,
            "evidence": evidence_meta,
        },
    )


def build_address_benchmark_dataset(
    rows: list[dict[str, Any]],
    *,
    evidence_rows: list[dict[str, Any]] | None = None,
    config: AddressBenchmarkConfig | None = None,
    pickup: str | None = None,
    delivery: str | None = None,
    now: datetime | None = None,
    source_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the benchmark payload from already-loaded read-only rows."""

    config = config or AddressBenchmarkConfig.from_env()
    now = _ensure_aware(now or datetime.now(timezone.utc))
    period_end = now.date()
    period_start = period_end - timedelta(days=config.period_days - 1)
    normalized_evidence = [_normalize_evidence(row) for row in evidence_rows or []]
    normalized_evidence = [row for row in normalized_evidence if row]

    route_instances: list[dict[str, Any]] = []
    invalid_rows = 0
    for row in rows:
        instance = _normalize_route_instance(row, config=config)
        if not instance:
            invalid_rows += 1
            continue
        row_day = instance["route_date"]
        if row_day < period_start or row_day > period_end:
            continue
        if pickup and not _filter_match(instance["pickup_address"], pickup):
            continue
        if delivery and not _filter_match(instance["delivery_address"], delivery):
            continue
        route_instances.append(instance)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for instance in route_instances:
        grouped[instance["address_pair_key"]].append(instance)

    address_pairs = [
        _build_pair_benchmark(
            pair_rows,
            evidence_rows=normalized_evidence,
            config=config,
        )
        for pair_rows in grouped.values()
    ]
    address_pairs = [
        pair
        for pair in address_pairs
        if pair["measured_orders"] >= config.minimum_history_samples
    ]
    address_pairs.sort(
        key=lambda item: (
            -float(item["opportunity_minutes_vs_pair_average"] or 0),
            -int(item["measured_orders"]),
            item["pickup_address"],
            item["delivery_address"],
        )
    )
    address_pairs = address_pairs[: config.max_pairs]

    measured_orders = sum(int(pair["measured_orders"]) for pair in address_pairs)
    opportunity_minutes = round(
        sum(float(pair["opportunity_minutes_vs_pair_average"] or 0) for pair in address_pairs),
        1,
    )
    evidence_matches = sum(
        int(pair["evidence"]["voice_recordings"]["match_count"])
        + int(pair["evidence"]["emails"]["match_count"])
        for pair in address_pairs
    )
    return {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "projection_mode": PROJECTION_MODE,
        "source_authority": SOURCE_AUTHORITY,
        "period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
            "days": config.period_days,
        },
        "thresholds": {
            "stop_threshold_minutes": config.stop_threshold_minutes,
            "minimum_history_samples": config.minimum_history_samples,
            "cost_per_truck_hour": config.cost_per_truck_hour,
        },
        "filters": {
            "pickup": pickup,
            "delivery": delivery,
        },
        "summary": {
            "address_pairs": len(address_pairs),
            "route_rows_read": len(rows),
            "route_rows_in_period": len(route_instances),
            "invalid_route_rows": invalid_rows,
            "measured_orders": measured_orders,
            "drivers_compared": _unique_driver_count(address_pairs),
            "opportunity_minutes_vs_pair_average": opportunity_minutes,
            "estimated_opportunity_cost_vs_pair_average": _money_from_minutes(
                opportunity_minutes,
                config.cost_per_truck_hour,
            ),
            "evidence_matches": evidence_matches,
        },
        "address_pairs": address_pairs,
        "evidence_sources": _build_evidence_source_status(source_meta, normalized_evidence, config),
        "source_meta": source_meta or {},
        "recommendations": _build_recommendations(address_pairs, config),
    }


def _load_xcelerator_route_rows(
    *,
    config: AddressBenchmarkConfig,
    period_start: date,
    period_end: date,
    store: XceleratorReviewOrdersStateStore | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    configured_source = _route_source(config)
    fallback_errors: list[str] = []
    if configured_source in {ROUTE_SOURCE_AUTO, ROUTE_SOURCE_FABRIC_WAREHOUSE}:
        warehouse_config = FabricWarehouseSqlConfig.from_env("FLEETPULSE_XCELERATOR_WAREHOUSE_SQL")
        if warehouse_config.configured:
            try:
                rows, meta = _load_fabric_warehouse_route_rows(
                    config=config,
                    warehouse_config=warehouse_config,
                    period_start=period_start,
                    period_end=period_end,
                )
                meta["configured_xcelerator_source"] = configured_source
                meta["effective_xcelerator_source"] = ROUTE_SOURCE_FABRIC_WAREHOUSE
                return rows, meta
            except Exception as exc:
                fallback_errors.append(f"fabric_warehouse_sql:{type(exc).__name__}")
                if configured_source == ROUTE_SOURCE_FABRIC_WAREHOUSE:
                    return [], {
                        "status": "unavailable",
                        "source_authority": "K1 Group LLC / Xcelerator Fabric Warehouse",
                        "projection_mode": PROJECTION_MODE,
                        "configured_xcelerator_source": configured_source,
                        "effective_xcelerator_source": ROUTE_SOURCE_FABRIC_WAREHOUSE,
                        "message": f"Xcelerator Fabric Warehouse unavailable: {type(exc).__name__}",
                        "required_config": ["FLEETPULSE_XCELERATOR_WAREHOUSE_SQL_*"],
                    }
        elif configured_source == ROUTE_SOURCE_FABRIC_WAREHOUSE:
            return [], {
                "status": "unavailable",
                "source_authority": "K1 Group LLC / Xcelerator Fabric Warehouse",
                "projection_mode": PROJECTION_MODE,
                "configured_xcelerator_source": configured_source,
                "effective_xcelerator_source": ROUTE_SOURCE_FABRIC_WAREHOUSE,
                "message": "Xcelerator Fabric Warehouse SQL is not configured.",
                "required_config": ["FLEETPULSE_XCELERATOR_WAREHOUSE_SQL_*"],
            }

    try:
        rows = (store or XceleratorReviewOrdersStateStore()).rows()
        return rows, {
            "status": "healthy",
            "source_authority": "K1 Group LLC / Xcelerator ReviewOrders export",
            "projection_mode": PROJECTION_MODE,
            "configured_xcelerator_source": configured_source,
            "effective_xcelerator_source": ROUTE_SOURCE_REVIEW_ORDERS_STATE,
            "row_count": len(rows),
            "fallback_errors": fallback_errors,
        }
    except XceleratorReviewOrdersStateTooLarge as exc:
        return [], {
            "status": "unavailable",
            "source_authority": "K1 Group LLC / Xcelerator ReviewOrders export",
            "projection_mode": PROJECTION_MODE,
            "configured_xcelerator_source": configured_source,
            "effective_xcelerator_source": ROUTE_SOURCE_REVIEW_ORDERS_STATE,
            "message": "ReviewOrders state is too large for synchronous benchmark reads.",
            "state_path": str(exc.path),
            "state_size_bytes": exc.size,
            "max_sync_state_bytes": exc.max_size,
            "fallback_errors": fallback_errors,
            "required_config": [
                "FLEETPULSE_XCELERATOR_REVIEW_ORDERS_ALLOW_LARGE_STATE_READ",
                "FLEETPULSE_XCELERATOR_REVIEW_ORDERS_MAX_SYNC_STATE_BYTES",
            ],
        }
    except Exception as exc:
        return [], {
            "status": "unavailable",
            "source_authority": "K1 Group LLC / Xcelerator ReviewOrders export",
            "projection_mode": PROJECTION_MODE,
            "configured_xcelerator_source": configured_source,
            "effective_xcelerator_source": ROUTE_SOURCE_REVIEW_ORDERS_STATE,
            "message": f"ReviewOrders state unavailable: {type(exc).__name__}",
            "fallback_errors": fallback_errors,
            "required_config": ["FLEETPULSE_XCELERATOR_REVIEW_ORDERS_STATE_PATH"],
        }


def _load_fabric_warehouse_route_rows(
    *,
    config: AddressBenchmarkConfig,
    warehouse_config: FabricWarehouseSqlConfig,
    period_start: date,
    period_end: date,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    table_rows = execute_sql_query(warehouse_config, _warehouse_table_discovery_sql())
    if not table_rows:
        raise RuntimeError("xcelerator_review_orders_table_not_found")
    table_schema = str(table_rows[0].get("table_schema") or "dbo")
    table_name = str(table_rows[0].get("table_name") or "xcelerator_review_orders")
    column_rows = execute_sql_query(warehouse_config, _warehouse_columns_sql(table_schema, table_name))
    columns = [str(row.get("column_name") or "") for row in column_rows if row.get("column_name")]
    resolution = _warehouse_column_resolution(columns)
    if resolution["missing"]:
        raise RuntimeError("xcelerator_review_orders_missing_columns:" + ",".join(resolution["missing"]))
    query = _warehouse_address_history_sql(
        table_schema=table_schema,
        table_name=table_name,
        resolution=resolution,
        period_start=period_start,
        period_end=period_end,
        max_rows=config.max_source_rows,
    )
    rows = execute_sql_query(warehouse_config, query)
    return rows, {
        "status": "healthy",
        "source_authority": "K1 Group LLC / Xcelerator Fabric Warehouse",
        "projection_mode": PROJECTION_MODE,
        "table": f"{table_schema}.{table_name}",
        "row_count": len(rows),
        "column_resolution": resolution["selected"],
    }


def _route_source(config: AddressBenchmarkConfig) -> str:
    source = str(config.xcelerator_source or ROUTE_SOURCE_AUTO).strip().casefold()
    if source in {"fabric", "fabric_warehouse", "fabric_warehouse_sql", "warehouse", "warehouse_sql"}:
        return ROUTE_SOURCE_FABRIC_WAREHOUSE
    if source in {"state", "review_orders", "review_orders_state", "local_state", "export"}:
        return ROUTE_SOURCE_REVIEW_ORDERS_STATE
    return ROUTE_SOURCE_AUTO


def _quote_sql_identifier(value: str) -> str:
    return f"[{value.replace(']', ']]')}]"


def _quote_sql_literal(value: str) -> str:
    return f"'{value.replace(chr(39), chr(39) + chr(39))}'"


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
    SUM(CASE WHEN {normalized_name} IN ('ordertrackingid', 'orderid', 'loadid', 'shipmentid') THEN 1 ELSE 0 END) > 0
    AND SUM(CASE WHEN {normalized_name} IN ('pickupaddress', 'pickuplocation', 'pickupcity', 'origin') THEN 1 ELSE 0 END) > 0
    AND SUM(CASE WHEN {normalized_name} IN ('deliveryaddress', 'deliverylocation', 'deliverycity', 'destination') THEN 1 ELSE 0 END) > 0
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


def _pick_column(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    normalized = {_normalize_key(column): column for column in columns}
    for alias in aliases:
        match = normalized.get(_normalize_key(alias))
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


def _warehouse_column_resolution(columns: list[str]) -> dict[str, Any]:
    order_id_column = _pick_column(
        columns,
        ("order_tracking_id", "OrderTrackingID", "Order Tracking ID", "Order ID", "OrderId", "Load ID", "Shipment ID"),
    )
    driver_id_column = _pick_column(columns, ("driver_no", "DriverNo", "Driver No", "Driver", "driver_id"))
    pickup_column = _pick_column(
        columns,
        ("pickup_address", "pickup_location", "pickup_city", "Pickup City", "origin", "Pickup"),
    )
    delivery_column = _pick_column(
        columns,
        ("delivery_address", "delivery_location", "delivery_city", "Delivery City", "destination", "Delivery"),
    )
    date_column = _pick_column(
        columns,
        ("pickup_target_from", "[P]From Date", "PFrom Date", "From Date", "[P]From", "PFrom", "Order Date", "date"),
    )
    start_columns = _pick_columns(
        columns,
        (
            "pickup_departure",
            "Pickup Departure",
            "[P]Departure",
            "PDeparture",
            "picked_up_at",
            "pickup_actual",
            "actual_pickup",
            "p_arrival",
            "Pickup Arrival",
            "[P]Arrival",
            "PArrival",
        ),
    )
    finish_columns = _pick_columns(
        columns,
        (
            "delivery_arrival",
            "Delivery Arrival",
            "[D]Arrival",
            "DArrival",
            "actual_delivery",
            "delivery_actual",
            "pod_datetime",
            "POD DateTime",
            "PODDateTime",
            "rt_pod_datetime",
            "RT POD DateTime",
            "delivered_at",
        ),
    )
    route_minutes_column = _pick_column(
        columns,
        ("actual_route_minutes", "route_minutes", "route_duration_minutes", "duration_minutes", "Route Minutes"),
    )
    stop_minutes_column = _pick_column(
        columns,
        (
            "long_stop_minutes",
            "geotab_stop_minutes",
            "stopped_minutes",
            "stop_minutes",
            "idle_minutes",
            "dwell_minutes",
            "detention_minutes",
        ),
    )
    stop_address_column = _pick_column(
        columns,
        (
            "long_stop_address",
            "geotab_stop_address",
            "stop_address",
            "stopped_address",
            "idle_address",
            "dwell_address",
            "detention_address",
            "stop_location",
            "nearest_stop_address",
        ),
    )
    stop_geofence_column = _pick_column(
        columns,
        (
            "long_stop_geofence",
            "geotab_stop_geofence",
            "stop_geofence",
            "geofence",
            "geofence_name",
            "zone_name",
            "site_name",
        ),
    )
    revenue_column = _pick_column(columns, ("Grand Total", "grand_total", "GrandTotal", "Revenue"))
    driver_pay_column = _pick_column(columns, ("Driver Pay", "driver_pay", "DriverPay"))
    selected = {
        "order_id_column": order_id_column,
        "driver_id_column": driver_id_column,
        "pickup_column": pickup_column,
        "delivery_column": delivery_column,
        "date_column": date_column,
        "start_columns": start_columns,
        "finish_columns": finish_columns,
        "route_minutes_column": route_minutes_column,
        "stop_minutes_column": stop_minutes_column,
        "stop_address_column": stop_address_column,
        "stop_geofence_column": stop_geofence_column,
        "revenue_column": revenue_column,
        "driver_pay_column": driver_pay_column,
    }
    missing = [
        name
        for name, value in (
            ("order_id", order_id_column),
            ("pickup_address", pickup_column),
            ("delivery_address", delivery_column),
            ("date", date_column),
        )
        if not value
    ]
    if not route_minutes_column and not (start_columns and finish_columns):
        missing.append("actual_route_time")
    return {"selected": selected, "missing": missing}


def _datetime_sql(column: str) -> str:
    return f"TRY_CONVERT(datetime2, {_quote_sql_identifier(column)})"


def _number_sql(column: str | None) -> str:
    if not column:
        return "CAST(NULL AS float)"
    return f"TRY_CONVERT(float, {_quote_sql_identifier(column)})"


def _string_sql(column: str | None, length: int = 255) -> str:
    if not column:
        return f"CAST(NULL AS varchar({length}))"
    return f"CAST({_quote_sql_identifier(column)} AS varchar({length}))"


def _coalesce_datetime_sql(columns: list[str]) -> str:
    expressions = [_datetime_sql(column) for column in columns]
    if not expressions:
        return "CAST(NULL AS datetime2)"
    if len(expressions) == 1:
        return expressions[0]
    return "COALESCE(" + ", ".join(expressions) + ")"


def _warehouse_address_history_sql(
    *,
    table_schema: str,
    table_name: str,
    resolution: dict[str, Any],
    period_start: date,
    period_end: date,
    max_rows: int,
) -> str:
    selected = resolution["selected"]
    table_ref = f"{_quote_sql_identifier(table_schema)}.{_quote_sql_identifier(table_name)}"
    date_expr = _datetime_sql(selected["date_column"])
    start_expr = _coalesce_datetime_sql(selected["start_columns"])
    finish_expr = _coalesce_datetime_sql(selected["finish_columns"])
    return f"""
SELECT TOP ({max_rows})
    {_string_sql(selected["order_id_column"], 128)} AS order_id,
    {_string_sql(selected["driver_id_column"], 128)} AS driver_id,
    {_string_sql(selected["driver_id_column"], 128)} AS driver_name,
    {_string_sql(selected["pickup_column"], 512)} AS pickup_address,
    {_string_sql(selected["delivery_column"], 512)} AS delivery_address,
    CONVERT(varchar(33), {start_expr}, 126) AS pickup_departure,
    CONVERT(varchar(33), {finish_expr}, 126) AS delivery_arrival,
    {_number_sql(selected["route_minutes_column"])} AS route_minutes,
    {_number_sql(selected["stop_minutes_column"])} AS stop_minutes,
    {_string_sql(selected["stop_address_column"], 512)} AS stop_address,
    {_string_sql(selected["stop_geofence_column"], 255)} AS stop_geofence,
    {_number_sql(selected["revenue_column"])} AS revenue,
    {_number_sql(selected["driver_pay_column"])} AS driver_pay,
    CONVERT(varchar(33), {date_expr}, 126) AS date
FROM {table_ref}
WHERE {date_expr} >= '{period_start.isoformat()}'
    AND {date_expr} < '{(period_end + timedelta(days=1)).isoformat()}'
    AND {_quote_sql_identifier(selected["pickup_column"])} IS NOT NULL
    AND {_quote_sql_identifier(selected["delivery_column"])} IS NOT NULL
ORDER BY {date_expr} DESC
""".strip()


def _load_evidence_rows(config: AddressBenchmarkConfig) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not config.evidence_path:
        return [], {
            "status": "pending_config",
            "source_authority": "Configured read-only voice/email evidence",
            "projection_mode": PROJECTION_MODE,
            "message": "No voice/email evidence feed configured for address benchmarks.",
            "required_config": ["FLEETPULSE_ADDRESS_BENCHMARK_EVIDENCE_PATH"],
        }

    path = Path(config.evidence_path)
    if not path.exists():
        return [], {
            "status": "unavailable",
            "source_authority": "Configured read-only voice/email evidence",
            "projection_mode": PROJECTION_MODE,
            "message": "Configured voice/email evidence path does not exist.",
            "path": str(path),
        }

    try:
        rows = _load_rows_from_text(path.read_text(encoding="utf-8"), filename=path.name)
        return rows, {
            "status": "healthy",
            "source_authority": "Configured read-only voice/email evidence",
            "projection_mode": PROJECTION_MODE,
            "path": str(path),
            "row_count": len(rows),
        }
    except Exception as exc:
        return [], {
            "status": "unavailable",
            "source_authority": "Configured read-only voice/email evidence",
            "projection_mode": PROJECTION_MODE,
            "message": f"Evidence feed unavailable: {type(exc).__name__}",
            "path": str(path),
        }


def _normalize_route_instance(
    row: dict[str, Any],
    *,
    config: AddressBenchmarkConfig,
) -> dict[str, Any] | None:
    pickup_address = _first_text(
        row,
        (
            "pickup_address",
            "pickupAddress",
            "pickup_location",
            "pickupLocation",
            "pickup_city",
            "Pickup City",
            "origin",
            "Origin",
            "Pickup",
        ),
    )
    delivery_address = _first_text(
        row,
        (
            "delivery_address",
            "deliveryAddress",
            "delivery_location",
            "deliveryLocation",
            "delivery_city",
            "Delivery City",
            "destination",
            "Destination",
            "Delivery",
        ),
    )
    if not pickup_address or not delivery_address:
        return None

    explicit_minutes = _positive_number(
        _find_value(
            row,
            (
                "actual_route_minutes",
                "route_minutes",
                "route_duration_minutes",
                "duration_minutes",
                "Route Minutes",
            ),
        )
    )
    start_at = _first_datetime(
        row,
        (
            "pickup_departure",
            "Pickup Departure",
            "[P]Departure",
            "PDeparture",
            "picked_up_at",
            "pickup_actual",
            "actual_pickup",
            "p_arrival",
            "Pickup Arrival",
            "[P]Arrival",
            "PArrival",
        ),
    )
    finish_at = _first_datetime(
        row,
        (
            "delivery_arrival",
            "Delivery Arrival",
            "[D]Arrival",
            "DArrival",
            "actual_delivery",
            "delivery_actual",
            "pod_datetime",
            "POD DateTime",
            "PODDateTime",
            "rt_pod_datetime",
            "RT POD DateTime",
            "delivered_at",
        ),
    )

    route_minutes = explicit_minutes
    duration_source = "explicit_route_minutes" if explicit_minutes is not None else None
    if route_minutes is None and start_at and finish_at and finish_at > start_at:
        route_minutes = round((finish_at - start_at).total_seconds() / 60, 1)
        duration_source = "actual_xcelerator_timestamps"

    route_date = (
        _first_date(
            row,
            (
                "pickup_departure",
                "Pickup Departure",
                "[P]Departure",
                "PDeparture",
                "pickup_actual",
                "actual_pickup",
                "pickup_target_from",
                "[P]From",
                "PFrom",
                "[P]From Date",
                "PFrom Date",
                "Order Date",
                "date",
            ),
        )
        or (start_at.date() if start_at else None)
        or (finish_at.date() if finish_at else None)
    )
    if not route_date:
        return None

    order_id = _first_text(
        row,
        (
            "order_tracking_id",
            "OrderTrackingID",
            "Order Tracking ID",
            "Order ID",
            "OrderId",
            "Load ID",
            "Shipment ID",
            "ticket_id",
        ),
    )
    driver_id = _first_text(
        row,
        ("driver_id", "driverId", "driver_no", "DriverNo", "Driver No", "Driver"),
    )
    driver_name = _first_text(
        row,
        ("driver_name", "driverName", "Driver Name", "Driver", "driver_no", "DriverNo"),
    )
    stop_minutes = _positive_number(
        _find_value(
            row,
            (
                "long_stop_minutes",
                "geotab_stop_minutes",
                "stopped_minutes",
                "stop_minutes",
                "idle_minutes",
                "dwell_minutes",
                "detention_minutes",
            ),
        )
    )
    stop_address = _first_text(
        row,
        (
            "long_stop_address",
            "geotab_stop_address",
            "stop_address",
            "stopped_address",
            "idle_address",
            "dwell_address",
            "detention_address",
            "stop_location",
            "nearest_stop_address",
        ),
    )
    stop_geofence = _first_text(
        row,
        (
            "long_stop_geofence",
            "geotab_stop_geofence",
            "stop_geofence",
            "geofence",
            "geofence_name",
            "zone_name",
            "site_name",
        ),
    )
    address_pair_key = _address_pair_key(pickup_address, delivery_address)
    return {
        "order_id": order_id or _stable_id("order", pickup_address, delivery_address, route_date.isoformat(), driver_id),
        "driver_id": driver_id,
        "driver_name": driver_name or driver_id or "Unassigned",
        "pickup_address": pickup_address,
        "delivery_address": delivery_address,
        "address_pair_key": address_pair_key,
        "route_date": route_date,
        "route_start_at": _iso(start_at),
        "route_finish_at": _iso(finish_at),
        "route_minutes": route_minutes,
        "duration_source": duration_source,
        "stop_minutes": stop_minutes,
        "stop_address": stop_address,
        "stop_geofence": stop_geofence,
        "stop_over_threshold": bool(stop_minutes is not None and stop_minutes >= config.stop_threshold_minutes),
        "revenue": _positive_number(
            _find_value(row, ("Grand Total", "grand_total", "GrandTotal", "Revenue"))
        )
        or 0.0,
        "driver_pay": _positive_number(
            _find_value(row, ("Driver Pay", "driver_pay", "DriverPay"))
        )
        or 0.0,
        "source_authority": "K1 Group LLC / Xcelerator ReviewOrders row",
        "projection_mode": PROJECTION_MODE,
    }


def _normalize_evidence(row: dict[str, Any]) -> dict[str, Any] | None:
    evidence_type = _normalize_key(
        _first_text(row, ("evidence_type", "type", "source_type", "channel")) or ""
    )
    if evidence_type not in VOICE_TYPES | EMAIL_TYPES:
        return None
    pickup_address = _first_text(row, ("pickup_address", "pickup", "origin", "pickup_location"))
    delivery_address = _first_text(row, ("delivery_address", "delivery", "destination", "delivery_location"))
    order_id = _first_text(row, ("order_id", "order_tracking_id", "OrderTrackingID", "ticket_id"))
    driver_id = _first_text(row, ("driver_id", "driver_no", "DriverNo", "Driver"))
    if not any((order_id, pickup_address and delivery_address)):
        return None
    summary = _truncate(
        _first_text(row, ("summary", "issue_summary", "notes", "body_preview", "transcript_summary")),
        240,
    )
    transcript = _first_text(row, ("transcript", "transcript_text", "recording_transcript"))
    return {
        "evidence_type": "voice_recording" if evidence_type in VOICE_TYPES else "email",
        "source_system": _first_text(row, ("source_system", "source", "mailbox", "folder")) or "configured evidence feed",
        "order_id": order_id,
        "driver_id": driver_id,
        "pickup_address": pickup_address,
        "delivery_address": delivery_address,
        "address_pair_key": _address_pair_key(pickup_address, delivery_address)
        if pickup_address and delivery_address
        else None,
        "occurred_at": _iso(_first_datetime(row, ("occurred_at", "received_at", "sent_at", "call_at", "date"))),
        "subject": _truncate(_first_text(row, ("subject", "title", "filename")), 140),
        "summary": summary,
        "transcript_available": bool(transcript),
        "source_uri": _safe_source_uri(
            _first_text(row, ("source_uri", "url", "web_url", "recording_url", "message_url"))
        ),
        "projection_mode": PROJECTION_MODE,
    }


def _build_pair_benchmark(
    rows: list[dict[str, Any]],
    *,
    evidence_rows: list[dict[str, Any]],
    config: AddressBenchmarkConfig,
) -> dict[str, Any]:
    rows = sorted(rows, key=lambda item: item["route_date"], reverse=True)
    measured = [row for row in rows if row.get("route_minutes") is not None]
    durations = [float(row["route_minutes"]) for row in measured]
    avg_minutes = round(sum(durations) / len(durations), 1) if durations else None
    best_minutes = round(min(durations), 1) if durations else None
    worst_minutes = round(max(durations), 1) if durations else None
    median_minutes = round(float(median(durations)), 1) if durations else None
    opportunity_minutes = (
        round(sum(max(0.0, float(row["route_minutes"]) - float(avg_minutes)) for row in measured), 1)
        if avg_minutes is not None
        else None
    )

    driver_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in measured:
        driver_buckets[str(row.get("driver_id") or row.get("driver_name") or "Unassigned")].append(row)

    driver_benchmarks = [
        _build_driver_benchmark(driver_rows, pair_average=avg_minutes, config=config)
        for driver_rows in driver_buckets.values()
    ]
    driver_benchmarks.sort(
        key=lambda item: (
            float(item["variance_vs_pair_average_minutes"] or 0),
            -int(item["measured_orders"]),
            item["driver_name"],
        )
    )

    pair_evidence = _match_evidence(rows, evidence_rows)
    return {
        "address_pair_key": rows[0]["address_pair_key"],
        "pickup_address": rows[0]["pickup_address"],
        "delivery_address": rows[0]["delivery_address"],
        "orders": len(rows),
        "measured_orders": len(measured),
        "missing_actual_time_orders": len(rows) - len(measured),
        "avg_route_minutes": avg_minutes,
        "median_route_minutes": median_minutes,
        "best_route_minutes": best_minutes,
        "worst_route_minutes": worst_minutes,
        "route_minutes_source": "actual Xcelerator timestamps or explicit actual route minutes",
        "stop_threshold_minutes": config.stop_threshold_minutes,
        "stop_events_over_threshold": sum(1 for row in rows if row.get("stop_over_threshold")),
        "opportunity_minutes_vs_pair_average": opportunity_minutes,
        "estimated_opportunity_cost_vs_pair_average": _money_from_minutes(
            opportunity_minutes,
            config.cost_per_truck_hour,
        ),
        "revenue_total": round(sum(float(row.get("revenue") or 0) for row in rows), 2),
        "driver_pay_total": round(sum(float(row.get("driver_pay") or 0) for row in rows), 2),
        "driver_benchmarks": driver_benchmarks,
        "recent_orders": _recent_order_summaries(rows, config.max_recent_orders_per_pair),
        "long_stop_evidence": _long_stop_summaries(rows, limit=5),
        "evidence": pair_evidence,
        "source_authority": "K1 Group LLC / Xcelerator ReviewOrders rows",
        "projection_mode": PROJECTION_MODE,
    }


def _build_driver_benchmark(
    rows: list[dict[str, Any]],
    *,
    pair_average: float | None,
    config: AddressBenchmarkConfig,
) -> dict[str, Any]:
    durations = [float(row["route_minutes"]) for row in rows if row.get("route_minutes") is not None]
    avg_minutes = round(sum(durations) / len(durations), 1) if durations else None
    variance = (
        round(float(avg_minutes) - float(pair_average), 1)
        if avg_minutes is not None and pair_average is not None
        else None
    )
    opportunity = (
        round(sum(max(0.0, float(row["route_minutes"]) - float(pair_average)) for row in rows), 1)
        if pair_average is not None
        else None
    )
    return {
        "driver_id": rows[0].get("driver_id"),
        "driver_name": rows[0].get("driver_name") or rows[0].get("driver_id") or "Unassigned",
        "measured_orders": len(durations),
        "avg_route_minutes": avg_minutes,
        "best_route_minutes": round(min(durations), 1) if durations else None,
        "worst_route_minutes": round(max(durations), 1) if durations else None,
        "variance_vs_pair_average_minutes": variance,
        "opportunity_minutes_vs_pair_average": opportunity,
        "estimated_opportunity_cost_vs_pair_average": _money_from_minutes(
            opportunity,
            config.cost_per_truck_hour,
        ),
        "stop_events_over_threshold": sum(1 for row in rows if row.get("stop_over_threshold")),
        "coaching_direction": _driver_direction(variance),
    }


def _recent_order_summaries(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    summaries = []
    for row in rows[:limit]:
        summaries.append(
            {
                "order_id": row["order_id"],
                "route_date": row["route_date"].isoformat(),
                "driver_id": row.get("driver_id"),
                "driver_name": row.get("driver_name"),
                "route_minutes": row.get("route_minutes"),
                "duration_source": row.get("duration_source"),
                "stop_minutes": row.get("stop_minutes"),
                "stop_address": row.get("stop_address"),
                "stop_geofence": row.get("stop_geofence"),
                "stop_over_threshold": row.get("stop_over_threshold"),
            }
        )
    return summaries


def _long_stop_summaries(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    summaries = []
    for row in rows:
        if not row.get("stop_over_threshold"):
            continue
        summaries.append(
            {
                "order_id": row["order_id"],
                "route_date": row["route_date"].isoformat(),
                "driver_id": row.get("driver_id"),
                "driver_name": row.get("driver_name"),
                "stop_minutes": row.get("stop_minutes"),
                "stop_address": row.get("stop_address"),
                "stop_geofence": row.get("stop_geofence"),
                "source_authority": "Configured stop/dwell evidence fields",
                "projection_mode": PROJECTION_MODE,
            }
        )
        if len(summaries) >= limit:
            break
    return summaries


def _match_evidence(
    route_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    order_ids = {str(row.get("order_id") or "").casefold() for row in route_rows if row.get("order_id")}
    pair_keys = {row.get("address_pair_key") for row in route_rows if row.get("address_pair_key")}
    matches = []
    for evidence in evidence_rows:
        evidence_order = str(evidence.get("order_id") or "").casefold()
        if evidence_order and evidence_order in order_ids:
            matches.append(evidence)
            continue
        if evidence.get("address_pair_key") in pair_keys:
            matches.append(evidence)

    voice = [row for row in matches if row["evidence_type"] == "voice_recording"]
    emails = [row for row in matches if row["evidence_type"] == "email"]
    return {
        "voice_recordings": _evidence_bucket(voice, "voice recordings"),
        "emails": _evidence_bucket(emails, "emails"),
    }


def _evidence_bucket(rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    return {
        "status": "matched" if rows else "no_matching_evidence",
        "match_count": len(rows),
        "matches": [
            {
                "source_system": row.get("source_system"),
                "order_id": row.get("order_id"),
                "driver_id": row.get("driver_id"),
                "occurred_at": row.get("occurred_at"),
                "subject": row.get("subject"),
                "summary": row.get("summary"),
                "transcript_available": row.get("transcript_available"),
                "source_uri": row.get("source_uri"),
            }
            for row in rows[:5]
        ],
        "message": (
            f"Configured read-only evidence feed has matching {label}."
            if rows
            else f"No configured read-only {label} matched this pickup/delivery pair."
        ),
    }


def _build_evidence_source_status(
    source_meta: dict[str, Any] | None,
    evidence_rows: list[dict[str, Any]],
    config: AddressBenchmarkConfig,
) -> dict[str, Any]:
    meta = (source_meta or {}).get("evidence") or {}
    voice_count = sum(1 for row in evidence_rows if row.get("evidence_type") == "voice_recording")
    email_count = sum(1 for row in evidence_rows if row.get("evidence_type") == "email")
    return {
        "status": meta.get("status", "pending_config"),
        "source_authority": meta.get("source_authority", "Configured read-only voice/email evidence"),
        "projection_mode": PROJECTION_MODE,
        "message": meta.get("message", ""),
        "required_config": meta.get("required_config", []),
        "path": meta.get("path") or config.evidence_path or None,
        "voice_recordings": voice_count,
        "emails": email_count,
    }


def _build_recommendations(
    address_pairs: list[dict[str, Any]],
    config: AddressBenchmarkConfig,
) -> list[str]:
    if not address_pairs:
        return [
            "Import or connect historical Xcelerator ReviewOrders rows with actual pickup and delivery timestamps before benchmarking driver speed.",
            "Configure a read-only voice/email evidence feed before using call recordings or email issues as root-cause proof.",
        ]
    recommendations = [
        "Use address-pair averages as a planning benchmark; keep Xcelerator as the operational source of truth.",
        "Review drivers above the pair average for dispatch timing, shipper dwell, receiver dwell, and documented accessorial causes before coaching or incentive changes.",
    ]
    if any(pair["stop_events_over_threshold"] for pair in address_pairs):
        recommendations.append(
            f"Prioritize rows with configured stop evidence over {config.stop_threshold_minutes} minutes before changing driver pay or route expectations."
        )
    if config.cost_per_truck_hour is None:
        recommendations.append(
            "Configure FLEETPULSE_ADDRESS_BENCHMARK_COST_PER_TRUCK_HOUR to convert recoverable minutes into a company cost estimate."
        )
    return recommendations


def _driver_direction(variance: float | None) -> str:
    if variance is None:
        return "Needs more measured trips before comparison."
    if variance <= -5:
        return "Potential benchmark driver; verify load and dwell comparability before using for incentives."
    if variance >= 15:
        return "Review dwell evidence and dispatch constraints before coaching."
    if variance >= 5:
        return "Slightly above pair average; monitor with more samples."
    return "Near pair average."


def _load_rows_from_text(content: str, *, filename: str = "") -> list[dict[str, Any]]:
    text = (content or "").lstrip("\ufeff").strip()
    if not text:
        return []
    suffix = Path(filename).suffix.casefold()
    if suffix in {".json", ".jsonl"} or text[:1] in {"[", "{"}:
        if suffix == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        payload = json.loads(text)
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            for key in ("rows", "evidence", "items", "value", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [row for row in value if isinstance(row, dict)]
            return [payload]
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in sample else csv.excel
    return [dict(row) for row in csv.DictReader(io.StringIO(text), dialect=dialect)]


def _find_value(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    normalized = {_normalize_key(alias) for alias in aliases}
    for key, value in row.items():
        if _normalize_key(key) in normalized:
            return value
    return None


def _first_text(row: dict[str, Any], aliases: tuple[str, ...]) -> str:
    value = _find_value(row, aliases)
    return str(value or "").strip()


def _first_datetime(row: dict[str, Any], aliases: tuple[str, ...]) -> datetime | None:
    return _parse_datetime(_find_value(row, aliases))


def _first_date(row: dict[str, Any], aliases: tuple[str, ...]) -> date | None:
    value = _find_value(row, aliases)
    parsed = _parse_datetime(value)
    if parsed:
        return parsed.date()
    if isinstance(value, date):
        return value
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        if value > 1_000_000_000_000:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        if value > 1_000_000_000:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if value > 20000:
            parsed_date = date(1899, 12, 30) + timedelta(days=int(value))
            return datetime.combine(parsed_date, datetime.min.time(), tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        return _ensure_aware(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%y %H:%M",
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%y %I:%M:%S %p",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%y %I:%M %p",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
    ):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _positive_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return max(float(value), 0.0)
    text = str(value).strip().replace("$", "").replace(",", "")
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    return max(float(match.group(0)), 0.0)


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _address_pair_key(pickup: str, delivery: str) -> str:
    return _stable_id("address_pair", _normalize_place(pickup), _normalize_place(delivery))


def _normalize_place(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def _filter_match(value: str, needle: str) -> bool:
    return _normalize_place(needle) in _normalize_place(value)


def _stable_id(namespace: str, *parts: Any) -> str:
    joined = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(f"{namespace}:{joined}".encode("utf-8")).hexdigest()[:16]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _truncate(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."


def _safe_source_uri(value: str | None) -> str | None:
    uri = str(value or "").strip()
    if not uri:
        return None
    parsed = urlparse(uri)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return None
    return uri


def _money_from_minutes(minutes: float | None, hourly_rate: float | None) -> float | None:
    if minutes is None or hourly_rate is None:
        return None
    return round((float(minutes) / 60) * float(hourly_rate), 2)


def _unique_driver_count(address_pairs: list[dict[str, Any]]) -> int:
    drivers = set()
    for pair in address_pairs:
        for driver in pair["driver_benchmarks"]:
            drivers.add(driver.get("driver_id") or driver.get("driver_name"))
    return len(drivers)
