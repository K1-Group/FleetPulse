"""Entity-aware CPM and gross-margin rollups for FleetPulse.

The projection keeps source ownership intact:

- Geotab/AtoB/QBO provide K1 Logistics Inc operating cost evidence.
- Xcelerator ReviewOrders or its Power BI semantic model provides revenue and
  driver pay by delivery center.
- K1 Group LLC receives gross-margin target tracking only, not CPM.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from integrations.powerbi.execute_queries import (
    PowerBIExecuteQueriesConfig,
    execute_dax_query,
)
from integrations.xcelerator.review_orders_feed import (
    ReviewOrdersFeedConfig,
    load_review_orders_rows,
)
from services.operating_cost_service import get_operating_cost_snapshot


K1L_ENTITY = "K1 Logistics Inc"
K1G_ENTITY = "K1 Group LLC"
K1L_MARGIN_TARGET_PCT = 0.72
K1G_MARGIN_TARGET_PCT = 0.20
XCELERATOR_ENTITY_AUTHORITY = "K1 Group LLC / Xcelerator delivery-center revenue and driver pay"
ENTITY_MARGIN_AUTHORITY = (
    "Geotab miles/hours + AtoB fuel + QBO expenses + Xcelerator delivery-center revenue/pay"
)


@dataclass(frozen=True)
class EntityMarginConfig:
    """Runtime settings for entity margin rollups."""

    powerbi: PowerBIExecuteQueriesConfig
    review_orders_feed: ReviewOrdersFeedConfig

    @classmethod
    def from_env(cls) -> "EntityMarginConfig":
        entity_feed = ReviewOrdersFeedConfig.from_env("FLEETPULSE_XCELERATOR_ENTITY_MARGIN")
        if not entity_feed.configured:
            entity_feed = ReviewOrdersFeedConfig.from_env("FLEETPULSE_LANE_STABILITY")
        return cls(
            powerbi=PowerBIExecuteQueriesConfig.from_env("FLEETPULSE_XCELERATOR_CEO_POWERBI"),
            review_orders_feed=entity_feed,
        )


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _key_matches(key: Any, alias: str) -> bool:
    normalized_key = _normalize(key)
    normalized_alias = _normalize(alias)
    return normalized_key == normalized_alias or normalized_key.endswith(normalized_alias)


def _find_value(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for key, value in row.items():
        if any(_key_matches(key, alias) for alias in aliases):
            return value
    return None


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


def _coerce_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and value > 20000:
        return date(1899, 12, 30) + timedelta(days=int(value))
    text = str(value).strip()
    if not text:
        return None
    token = text.split()[0]
    try:
        return datetime.fromisoformat(token.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%m-%d-%y"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def _today() -> date:
    return datetime.now(timezone.utc).date()


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


def _week_key(day: date) -> str:
    return _week_start(day).isoformat()


def _week_windows(start: date, end: date) -> list[tuple[date, date]]:
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        week_end = min(_week_start(cursor) + timedelta(days=6), end)
        windows.append((cursor, week_end))
        cursor = week_end + timedelta(days=1)
    return windows


def _money(value: float) -> float:
    return round(float(value or 0), 2)


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _source(status: str, authority: str, *, message: str = "", row_count: int = 0) -> dict[str, Any]:
    return {
        "status": status,
        "source_authority": authority,
        "projection_mode": "read_only",
        "message": message,
        "row_count": row_count,
    }


def _entity_from_delivery_center(value: Any) -> str | None:
    normalized = _normalize(value)
    if not normalized or "test" in normalized:
        return None
    if "k1logistics" in normalized:
        return K1L_ENTITY
    if "k1group" in normalized:
        return K1G_ENTITY
    return None


def _row_day(row: dict[str, Any]) -> date | None:
    return _coerce_date(
        _find_value(
            row,
            (
                "WeekStart",
                "week_start",
                "pickup_target_from",
                "[P]From Date",
                "PFrom Date",
                "From Date",
                "Order Date",
                "date",
            ),
        )
    )


def _delivery_center(row: dict[str, Any]) -> str:
    return str(
        _find_value(
            row,
            ("delivery_center", "Delivery Center", "DeliveryCenter", "Delivery Center Name"),
        )
        or ""
    ).strip()


def _grand_total(row: dict[str, Any]) -> float:
    return _number(
        _find_value(
            row,
            (
                "GrandTotal",
                "Grand Total",
                "grand_total",
                "grand_total_amount",
                "Revenue",
            ),
        )
    )


def _driver_pay(row: dict[str, Any]) -> float:
    return _number(
        _find_value(
            row,
            ("DriverPay", "Driver Pay", "driver_pay", "driver_pay_amount"),
        )
    )


def _order_count(row: dict[str, Any]) -> int:
    explicit = _find_value(row, ("Orders", "orders", "OrderCount", "order_count"))
    if explicit not in (None, ""):
        return int(_number(explicit))
    return 1


def _empty_entity_week(start: date, end: date) -> dict[str, Any]:
    week = _week_start(start)
    return {
        "week_start": week.isoformat(),
        "week_end": end.isoformat(),
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "k1l_orders": 0,
        "k1l_grand_total": 0.0,
        "k1l_driver_pay": 0.0,
        "k1g_orders": 0,
        "k1g_grand_total": 0.0,
        "k1g_driver_pay": 0.0,
        "idle_hours": 0.0,
        "operating_hours": 0.0,
    }


def _build_powerbi_dax(start: date, end: date) -> str:
    return f"""
EVALUATE
VAR BaseRows =
    FILTER(
        ADDCOLUMNS(
            'xcelerator_review_orders',
            "PickupDate", DATEVALUE('xcelerator_review_orders'[pickup_target_from]),
            "WeekStart", DATEVALUE('xcelerator_review_orders'[pickup_target_from]) - WEEKDAY(DATEVALUE('xcelerator_review_orders'[pickup_target_from]), 2) + 1
        ),
        NOT ISBLANK('xcelerator_review_orders'[pickup_target_from])
            && [PickupDate] >= DATE({start.year}, {start.month}, {start.day})
            && [PickupDate] <= DATE({end.year}, {end.month}, {end.day})
    )
RETURN
GROUPBY(
    BaseRows,
    [WeekStart],
    'xcelerator_review_orders'[delivery_center],
    "GrandTotal", SUMX(CURRENTGROUP(), 'xcelerator_review_orders'[grand_total_amount]),
    "DriverPay", SUMX(CURRENTGROUP(), 'xcelerator_review_orders'[driver_pay_amount]),
    "Orders", COUNTX(CURRENTGROUP(), 'xcelerator_review_orders'[order_tracking_id])
)
ORDER BY [WeekStart], 'xcelerator_review_orders'[delivery_center]
""".strip()


def _load_powerbi_entity_rows(
    start: date,
    end: date,
    *,
    config: PowerBIExecuteQueriesConfig,
) -> list[dict[str, Any]]:
    if not config.configured:
        return []
    return execute_dax_query(config, _build_powerbi_dax(start, end))


def _fallback_feed_message(powerbi_error: str) -> str:
    if not powerbi_error:
        return ""
    return f"Power BI semantic model unavailable; used ReviewOrders feed fallback. {powerbi_error}"


def _load_xcelerator_entity_rows(
    start: date,
    end: date,
    *,
    config: EntityMarginConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    powerbi_error = ""
    if config.powerbi.configured:
        try:
            rows = _load_powerbi_entity_rows(start, end, config=config.powerbi)
            return rows, _source(
                "healthy" if rows else "awaiting_feed",
                XCELERATOR_ENTITY_AUTHORITY,
                message="" if rows else "Xcelerator CEO Dashboard semantic model returned no rows.",
                row_count=len(rows),
            ), "powerbi_semantic_model"
        except Exception as exc:
            powerbi_error = f"{type(exc).__name__}: {exc}"

    if not config.review_orders_feed.configured:
        return [], _source(
            "awaiting_feed",
            XCELERATOR_ENTITY_AUTHORITY,
            message=powerbi_error or "Xcelerator entity margin feed is not configured.",
        ), "unconfigured"

    try:
        rows = load_review_orders_rows(config.review_orders_feed)
    except Exception as exc:
        return [], _source(
            "unavailable",
            XCELERATOR_ENTITY_AUTHORITY,
            message=f"{type(exc).__name__}: {exc}",
        ), "review_orders_feed"

    return rows, _source(
        "healthy" if rows else "awaiting_feed",
        XCELERATOR_ENTITY_AUTHORITY,
        message=_fallback_feed_message(powerbi_error)
        if rows
        else "Xcelerator entity margin feed is configured, but no rows are available.",
        row_count=len(rows),
    ), "review_orders_feed"


def _xcelerator_entity_weekly(
    start: date,
    end: date,
    *,
    config: EntityMarginConfig,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], dict[str, int], str]:
    rows, source, source_type = _load_xcelerator_entity_rows(start, end, config=config)
    weekly = {
        _week_key(week_start): _empty_entity_week(week_start, week_end)
        for week_start, week_end in _week_windows(start, end)
    }
    excluded: dict[str, int] = {}
    included_dates: list[date] = []
    included_row_count = 0

    for row in rows:
        row_day = _row_day(row)
        if row_day is None:
            continue
        if source_type == "powerbi_semantic_model":
            week_start = _week_start(row_day)
            if week_start > end or week_start + timedelta(days=6) < start:
                continue
        elif not (start <= row_day <= end):
            continue
        center = _delivery_center(row)
        entity = _entity_from_delivery_center(center)
        if entity is None:
            if center:
                excluded[center] = excluded.get(center, 0) + _order_count(row)
            continue

        included_dates.append(row_day)
        included_row_count += _order_count(row)
        bucket = weekly.setdefault(_week_key(row_day), _empty_entity_week(row_day, row_day))
        if entity == K1L_ENTITY:
            bucket["k1l_orders"] += _order_count(row)
            bucket["k1l_grand_total"] += _grand_total(row)
            bucket["k1l_driver_pay"] += _driver_pay(row)
        else:
            bucket["k1g_orders"] += _order_count(row)
            bucket["k1g_grand_total"] += _grand_total(row)
            bucket["k1g_driver_pay"] += _driver_pay(row)

    for bucket in weekly.values():
        bucket["k1l_grand_total"] = _money(bucket["k1l_grand_total"])
        bucket["k1l_driver_pay"] = _money(bucket["k1l_driver_pay"])
        bucket["k1g_grand_total"] = _money(bucket["k1g_grand_total"])
        bucket["k1g_driver_pay"] = _money(bucket["k1g_driver_pay"])

    if source["status"] == "healthy" and not included_row_count:
        source = {
            **source,
            "status": "awaiting_feed",
            "message": "Xcelerator rows loaded, but none matched K1 Group LLC or K1 Logistics Inc delivery centers.",
        }
    elif (
        source["status"] == "healthy"
        and included_dates
        and source_type != "powerbi_semantic_model"
    ):
        source_status = "healthy"
        source_message = source.get("message") or ""
        if min(included_dates) > start or max(included_dates) < end:
            source_status = "partial"
            source_message = (
                f"Entity rows cover {min(included_dates).isoformat()}..{max(included_dates).isoformat()}, "
                f"not the full requested {start.isoformat()}..{end.isoformat()} period."
            )
        source = {
            **source,
            "status": source_status,
            "message": source_message,
            "row_count": included_row_count,
        }

    return weekly, source, excluded, source_type


def _finish_entity_week(row: dict[str, Any]) -> dict[str, Any]:
    k1l_revenue = float(row["k1l_grand_total"])
    miles = float(row["miles"])
    drive_hours = float(row["drive_hours"])
    operating_hours = float(row.get("operating_hours") or drive_hours)
    k1l_fuel_driver_cost = float(row["fuel_cost"]) + float(row["k1l_driver_pay"])
    k1l_true_cost = k1l_fuel_driver_cost + float(row["insurance_cost"]) + float(row["other_expense_cost"])
    qbo_expenses_available = bool(row["qbo_expenses_available"])
    k1l_profit = k1l_revenue - k1l_true_cost if qbo_expenses_available else None
    k1l_actual_margin_before_fuel = k1l_revenue - float(row["k1l_driver_pay"])
    k1l_actual_margin_after_fuel = k1l_actual_margin_before_fuel - float(row["fuel_cost"])
    k1g_actual_margin_before_overhead = float(row["k1g_grand_total"]) - float(row["k1g_driver_pay"])

    row.update(
        {
            "k1l_target_gross_margin": _money(k1l_revenue * K1L_MARGIN_TARGET_PCT),
            "k1l_actual_gross_margin_before_fuel": _money(k1l_actual_margin_before_fuel),
            "k1l_actual_gross_margin_pct_before_fuel": _ratio(
                k1l_actual_margin_before_fuel,
                k1l_revenue,
            ),
            "k1l_actual_gross_margin_after_fuel": _money(k1l_actual_margin_after_fuel),
            "k1l_actual_gross_margin_pct_after_fuel": _ratio(
                k1l_actual_margin_after_fuel,
                k1l_revenue,
            ),
            "k1l_revenue_per_mile": _ratio(k1l_revenue, miles),
            "k1l_revenue_per_drive_hour": _ratio(k1l_revenue, drive_hours),
            "k1l_revenue_per_engine_hour": _ratio(k1l_revenue, operating_hours),
            "k1l_driver_pay_cpm": _ratio(float(row["k1l_driver_pay"]), miles),
            "k1l_fuel_cpm": _ratio(float(row["fuel_cost"]), miles),
            "k1l_fuel_plus_driver_cpm": _ratio(k1l_fuel_driver_cost, miles),
            "k1l_true_operating_cpm": _ratio(k1l_true_cost, float(row["miles"]))
            if qbo_expenses_available
            else None,
            "k1l_true_operating_cost_per_drive_hour": _ratio(k1l_true_cost, drive_hours)
            if qbo_expenses_available
            else None,
            "k1l_true_operating_cost_per_engine_hour": _ratio(k1l_true_cost, operating_hours)
            if qbo_expenses_available
            else None,
            "k1l_true_operating_cost": _money(k1l_true_cost)
            if qbo_expenses_available
            else None,
            "k1l_profit": _money(k1l_profit) if k1l_profit is not None else None,
            "k1l_profit_per_mile": _ratio(k1l_profit, miles) if k1l_profit is not None else None,
            "k1l_profit_per_drive_hour": _ratio(k1l_profit, drive_hours) if k1l_profit is not None else None,
            "k1l_profit_per_engine_hour": _ratio(k1l_profit, operating_hours) if k1l_profit is not None else None,
            "k1g_target_gross_margin": _money(float(row["k1g_grand_total"]) * K1G_MARGIN_TARGET_PCT),
            "k1g_actual_gross_margin_before_overhead": _money(
                k1g_actual_margin_before_overhead
            ),
            "k1g_actual_gross_margin_pct_before_overhead": _ratio(
                k1g_actual_margin_before_overhead,
                float(row["k1g_grand_total"]),
            ),
        }
    )
    return row


def _summary_from_weekly(weekly: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "miles": sum(float(row["miles"]) for row in weekly),
        "drive_hours": sum(float(row["drive_hours"]) for row in weekly),
        "idle_hours": sum(float(row.get("idle_hours") or 0) for row in weekly),
        "operating_hours": sum(float(row.get("operating_hours") or row["drive_hours"]) for row in weekly),
        "fuel_cost": sum(float(row["fuel_cost"]) for row in weekly),
        "insurance_cost": sum(float(row["insurance_cost"]) for row in weekly),
        "other_expense_cost": sum(float(row["other_expense_cost"]) for row in weekly),
        "k1l_orders": sum(int(row["k1l_orders"]) for row in weekly),
        "k1l_grand_total": sum(float(row["k1l_grand_total"]) for row in weekly),
        "k1l_driver_pay": sum(float(row["k1l_driver_pay"]) for row in weekly),
        "k1g_orders": sum(int(row["k1g_orders"]) for row in weekly),
        "k1g_grand_total": sum(float(row["k1g_grand_total"]) for row in weekly),
        "k1g_driver_pay": sum(float(row["k1g_driver_pay"]) for row in weekly),
    }
    qbo_expenses_available = all(row["qbo_expenses_available"] for row in weekly) if weekly else False
    row = {
        "miles": round(totals["miles"], 2),
        "drive_hours": round(totals["drive_hours"], 2),
        "idle_hours": round(totals["idle_hours"], 2),
        "operating_hours": round(totals["operating_hours"], 2),
        "fuel_cost": _money(totals["fuel_cost"]),
        "insurance_cost": _money(totals["insurance_cost"]),
        "other_expense_cost": _money(totals["other_expense_cost"]),
        "k1l_orders": totals["k1l_orders"],
        "k1l_grand_total": _money(totals["k1l_grand_total"]),
        "k1l_driver_pay": _money(totals["k1l_driver_pay"]),
        "k1g_orders": totals["k1g_orders"],
        "k1g_grand_total": _money(totals["k1g_grand_total"]),
        "k1g_driver_pay": _money(totals["k1g_driver_pay"]),
        "qbo_expenses_available": qbo_expenses_available,
    }
    return _finish_entity_week(row)


async def get_entity_margin_snapshot(
    *,
    days: int = 90,
    start: date | datetime | str | None = None,
    end: date | datetime | str | None = None,
    config: EntityMarginConfig | None = None,
) -> dict[str, Any]:
    """Return weekly K1L CPM and K1G/K1L margin-target rollups."""

    period_start, period_end = _resolve_window(days, start, end)
    config = config or EntityMarginConfig.from_env()

    operating_snapshot, entity_result = await asyncio.gather(
        get_operating_cost_snapshot(days=days, start=period_start, end=period_end),
        asyncio.to_thread(_xcelerator_entity_weekly, period_start, period_end, config=config),
    )
    entity_weekly, xcelerator_source, excluded_centers, xcelerator_source_type = entity_result

    operating_weekly = {
        str(row["week_start"]): row for row in operating_snapshot.get("weekly", [])
    }
    qbo_source = operating_snapshot.get("sources", {}).get("qbo_expenses", {})
    qbo_expenses_available = qbo_source.get("status") == "healthy"

    weekly_rows: list[dict[str, Any]] = []
    for week_start, week_end in _week_windows(period_start, period_end):
        key = _week_key(week_start)
        entity_row = entity_weekly.get(key, _empty_entity_week(week_start, week_end))
        operating_row = operating_weekly.get(key, {})
        row = {
            **entity_row,
            "miles": round(float(operating_row.get("miles") or 0), 2),
            "drive_hours": round(float(operating_row.get("drive_hours") or 0), 2),
            "idle_hours": round(float(operating_row.get("idle_hours") or 0), 2),
            "operating_hours": round(
                float(
                    operating_row.get("operating_hours")
                    or (
                        float(operating_row.get("drive_hours") or 0)
                        + float(operating_row.get("idle_hours") or 0)
                    )
                ),
                2,
            ),
            "fuel_cost": _money(float(operating_row.get("fuel_cost") or 0)),
            "insurance_cost": _money(float(operating_row.get("insurance_cost") or 0)),
            "other_expense_cost": _money(float(operating_row.get("other_expense_cost") or 0)),
            "qbo_expenses_available": qbo_expenses_available,
        }
        weekly_rows.append(_finish_entity_week(row))

    sources = {
        "telemetry": operating_snapshot.get("sources", {}).get("telemetry", {}),
        "fuel": operating_snapshot.get("sources", {}).get("fuel", {}),
        "xcelerator_entity": xcelerator_source,
        "qbo_expenses": qbo_source,
    }
    unresolved_sources = [
        name
        for name in ("telemetry", "fuel", "xcelerator_entity")
        if sources.get(name, {}).get("status") != "healthy"
    ]
    true_cpm_unresolved_sources = [
        name
        for name in ("telemetry", "fuel", "xcelerator_entity", "qbo_expenses")
        if sources.get(name, {}).get("status") != "healthy"
    ]

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_authority": ENTITY_MARGIN_AUTHORITY,
        "projection_mode": "read_only",
        "grain": "weekly",
        "k1l_margin_target_pct": K1L_MARGIN_TARGET_PCT,
        "k1g_margin_target_pct": K1G_MARGIN_TARGET_PCT,
        "complete_k1l_cpm_available": not unresolved_sources,
        "complete_k1l_true_cpm_available": not true_cpm_unresolved_sources,
        "unresolved_sources": unresolved_sources,
        "true_cpm_unresolved_sources": true_cpm_unresolved_sources,
        "xcelerator_source_type": xcelerator_source_type,
        "policy": {
            "k1l_delivery_center": K1L_ENTITY,
            "k1g_delivery_centers": ["K1 Group, LLC", K1G_ENTITY],
            "k1l_cpm_denominator": "Geotab miles for K1 Logistics Inc fleet operations",
            "k1g_cpm_denominator": None,
        },
        "sources": sources,
        "summary": _summary_from_weekly(weekly_rows),
        "weekly": weekly_rows,
        "excluded_delivery_centers": excluded_centers,
        "row_counts": {
            "weekly": len(weekly_rows),
            "excluded_delivery_centers": len(excluded_centers),
        },
    }
