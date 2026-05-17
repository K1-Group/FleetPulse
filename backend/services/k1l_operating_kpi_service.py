"""Read-only K1 Logistics operating-cost KPI snapshot.

This lightweight projection is for first-screen dashboard cards. It reads a
pre-approved monthly cost stack from environment configuration and does not
mutate Xcelerator, Geotab, QuickBooks, AtoB, or Power BI.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping

from integrations.powerbi.execute_queries import (
    PowerBIExecuteQueriesConfig,
    execute_dax_query,
)


DEFAULT_ENTITY = "K1 Logistics Inc"
DEFAULT_SOURCE = "QBO K1 Logistics P&L + Xcelerator revenue/driver pay + AtoB fuel + Geotab miles"
DEFAULT_METHOD = (
    "driver_pay + fuel + amex_fleet_maintenance + "
    "qbo_p_and_l_operating_expenses_excluding_repairs_maintenance"
)
MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")
POWERBI_REVENUE_SOURCE = "xcelerator_ceo_powerbi"
JSON_REVENUE_SOURCE = "monthly_json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _round(value: float, digits: int = 2) -> float:
    return round(float(value or 0), digits)


def _read_string(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _number(value: Any, field_name: str) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid K1L operating cost value for {field_name}") from exc


def _optional_number(value: Any, field_name: str) -> float | None:
    if value in (None, ""):
        return None
    return _number(value, field_name)


def _ratio(numerator: float | None, denominator: float) -> float | None:
    if numerator is None or denominator <= 0:
        return None
    return _round(numerator / denominator, 3)


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _key_matches(key: Any, alias: str) -> bool:
    normalized_key = _normalize(key)
    normalized_alias = _normalize(alias)
    return normalized_key == normalized_alias or normalized_key.endswith(normalized_alias)


def _find_value(row: Mapping[str, Any], aliases: tuple[str, ...]) -> Any:
    for key, value in row.items():
        if any(_key_matches(key, alias) for alias in aliases):
            return value
    return None


def _month_start(month: str) -> date:
    if not MONTH_PATTERN.match(month):
        raise ValueError(f'Invalid month "{month or "<blank>"}"')
    year, month_num = (int(part) for part in month.split("-", 1))
    return date(year, month_num, 1)


def _next_month(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def _coerce_month_key(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m")
    if isinstance(value, date):
        return value.strftime("%Y-%m")
    if isinstance(value, (int, float)) and value > 20000:
        return (date(1899, 12, 30) + timedelta(days=int(value))).strftime("%Y-%m")
    text = str(value or "").strip()
    if not text:
        return ""
    if MONTH_PATTERN.match(text[:7]):
        return text[:7]
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%m-%d-%y"):
        try:
            return datetime.strptime(text.split()[0], fmt).strftime("%Y-%m")
        except ValueError:
            continue
    return ""


def _resolve_rows(parsed_value: Any) -> list[dict[str, Any]]:
    if isinstance(parsed_value, list):
        return parsed_value
    if not isinstance(parsed_value, dict):
        return []
    rows = parsed_value.get("months") or parsed_value.get("monthly") or parsed_value.get("rows") or []
    return rows if isinstance(rows, list) else []


def _parse_monthly_json(raw_value: str) -> dict[str, Any]:
    if not raw_value:
        return {}
    parsed_value = json.loads(raw_value)
    return {
        "as_of_date": parsed_value.get("asOfDate") if isinstance(parsed_value, dict) else None,
        "excluded_accounts": parsed_value.get("excludedAccounts") if isinstance(parsed_value, dict) else None,
        "method": parsed_value.get("method") if isinstance(parsed_value, dict) else None,
        "monthly_rows": _resolve_rows(parsed_value),
        "source": parsed_value.get("source") if isinstance(parsed_value, dict) else None,
    }


def _config_from_env(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = env or os.environ
    parsed_json = _parse_monthly_json(_read_string(env.get("K1L_OPERATING_COST_MONTHLY_JSON")))
    revenue_source = _read_string(
        env.get("K1L_OPERATING_COST_REVENUE_SOURCE"),
        POWERBI_REVENUE_SOURCE,
    )
    return {
        "as_of_date": _read_string(
            parsed_json.get("as_of_date") or env.get("K1L_OPERATING_COST_CUTOFF_DATE")
        ),
        "entity": _read_string(env.get("K1L_OPERATING_COST_ENTITY"), DEFAULT_ENTITY),
        "excluded_accounts": parsed_json.get("excluded_accounts") or ["Repairs & maintenance"],
        "method": _read_string(
            parsed_json.get("method") or env.get("K1L_OPERATING_COST_METHOD"),
            DEFAULT_METHOD,
        ),
        "monthly_rows": parsed_json.get("monthly_rows") or [],
        "powerbi": PowerBIExecuteQueriesConfig.from_env("FLEETPULSE_XCELERATOR_CEO_POWERBI"),
        "revenue_source": revenue_source,
        "source": _read_string(
            parsed_json.get("source") or env.get("K1L_OPERATING_COST_SOURCE"),
            DEFAULT_SOURCE,
        ),
    }


def _build_powerbi_monthly_revenue_dax(start_month: str, end_month: str) -> str:
    start = _month_start(start_month)
    end = _next_month(_month_start(end_month)) - timedelta(days=1)
    return f"""
EVALUATE
VAR BaseRows =
    FILTER(
        ADDCOLUMNS(
            'xcelerator_review_orders',
            "PickupDate", DATEVALUE('xcelerator_review_orders'[pickup_target_from]),
            "MonthStart", DATE(YEAR(DATEVALUE('xcelerator_review_orders'[pickup_target_from])), MONTH(DATEVALUE('xcelerator_review_orders'[pickup_target_from])), 1)
        ),
        NOT ISBLANK('xcelerator_review_orders'[pickup_target_from])
            && [PickupDate] >= DATE({start.year}, {start.month}, {start.day})
            && [PickupDate] <= DATE({end.year}, {end.month}, {end.day})
    )
RETURN
GROUPBY(
    BaseRows,
    [MonthStart],
    'xcelerator_review_orders'[delivery_center],
    "GrandTotal", SUMX(CURRENTGROUP(), 'xcelerator_review_orders'[grand_total_amount]),
    "Orders", COUNTX(CURRENTGROUP(), 'xcelerator_review_orders'[order_tracking_id])
)
ORDER BY [MonthStart], 'xcelerator_review_orders'[delivery_center]
""".strip()


def _month_from_raw_row(row: Mapping[str, Any]) -> str:
    return _read_string(row.get("month") or row.get("period") or row.get("month_key"))


def _is_k1_logistics_center(value: Any) -> bool:
    return "k1logistics" in _normalize(value)


def _load_powerbi_k1l_monthly_revenue(
    rows: list[dict[str, Any]],
    *,
    config: PowerBIExecuteQueriesConfig,
) -> tuple[dict[str, float], dict[str, Any]]:
    months = sorted({_month_from_raw_row(row) for row in rows if MONTH_PATTERN.match(_month_from_raw_row(row))})
    if not months:
        return {}, {"status": "not_configured", "message": "No monthly rows available for revenue lookup."}
    if not config.configured:
        return {}, {
            "status": "not_configured",
            "message": "Power BI auth is not configured; using monthly JSON revenue when present.",
        }

    query = _build_powerbi_monthly_revenue_dax(months[0], months[-1])
    result_rows = execute_dax_query(config, query)
    revenue_by_month: dict[str, float] = {}
    included_rows = 0
    for row in result_rows:
        delivery_center = _find_value(
            row,
            ("delivery_center", "Delivery Center", "DeliveryCenter", "Delivery Center Name"),
        )
        if not _is_k1_logistics_center(delivery_center):
            continue
        month = _coerce_month_key(_find_value(row, ("MonthStart", "month_start", "PickupDate")))
        if month not in months:
            continue
        revenue_by_month[month] = revenue_by_month.get(month, 0.0) + _number(
            _find_value(row, ("GrandTotal", "Grand Total", "grand_total", "grand_total_amount", "Revenue")),
            f"{month}.xcelerator_revenue",
        )
        included_rows += int(_number(_find_value(row, ("Orders", "orders", "OrderCount", "order_count")), f"{month}.orders"))

    return {
        month: _round(revenue)
        for month, revenue in revenue_by_month.items()
    }, {
        "status": "healthy" if revenue_by_month else "awaiting_feed",
        "message": "" if revenue_by_month else "Power BI returned rows, but none matched K1 Logistics Inc monthly revenue.",
        "row_count": included_rows,
    }


def _merge_powerbi_revenue(
    rows: list[dict[str, Any]],
    *,
    config: PowerBIExecuteQueriesConfig,
    enabled: bool,
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    if not enabled:
        return rows, JSON_REVENUE_SOURCE, {
            "status": "disabled",
            "message": "K1L_OPERATING_COST_REVENUE_SOURCE is not xcelerator_ceo_powerbi.",
        }
    try:
        revenue_by_month, status = _load_powerbi_k1l_monthly_revenue(rows, config=config)
    except Exception as exc:
        return rows, JSON_REVENUE_SOURCE, {
            "status": "unavailable",
            "message": f"{type(exc).__name__}: {exc}; using monthly JSON revenue when present.",
        }
    if not revenue_by_month:
        return rows, JSON_REVENUE_SOURCE, status

    merged: list[dict[str, Any]] = []
    for row in rows:
        month = _month_from_raw_row(row)
        if month in revenue_by_month:
            merged.append({**row, "revenue": revenue_by_month[month]})
        else:
            merged.append(row)
    return merged, POWERBI_REVENUE_SOURCE, status


def normalize_k1l_operating_month(row: Mapping[str, Any]) -> dict[str, Any]:
    month = _read_string(row.get("month") or row.get("period") or row.get("month_key"))
    if not MONTH_PATTERN.match(month):
        raise ValueError(f'Invalid K1L operating cost month "{month or "<blank>"}"')

    miles = _number(row.get("miles") or row.get("milesDriven") or row.get("driveMiles"), f"{month}.miles")
    driver_pay = _number(row.get("driverPay") or row.get("driver_pay"), f"{month}.driverPay")
    fuel = _number(row.get("fuel") or row.get("fuelCost") or row.get("fuel_cost"), f"{month}.fuel")
    fleet_maintenance = _number(
        row.get("fleetMaintenance")
        or row.get("amexMaintenance")
        or row.get("maintenance")
        or row.get("fleet_maintenance"),
        f"{month}.fleetMaintenance",
    )
    payroll = _number(row.get("payroll") or row.get("employeeExpense"), f"{month}.payroll")
    other_ops = _number(
        row.get("otherOps") or row.get("otherOperatingExpense"),
        f"{month}.otherOps",
    )
    added_p_and_l_ops = (
        _number(
            row.get("addedPAndLOps") or row.get("addedPLOps") or row.get("qboOperatingExpense"),
            f"{month}.addedPAndLOps",
        )
        or payroll + other_ops
    )
    prior_cost = driver_pay + fuel + fleet_maintenance
    total_cost = prior_cost + added_p_and_l_ops
    revenue = _optional_number(
        row.get("revenue")
        or row.get("grossRevenue")
        or row.get("grandTotal")
        or row.get("grand_total")
        or row.get("k1lRevenue")
        or row.get("k1l_grand_total"),
        f"{month}.revenue",
    )
    gross_profit = _round(revenue - total_cost) if revenue is not None else None
    revenue_per_mile = _ratio(revenue, miles)
    cost_per_mile = _ratio(total_cost, miles)
    profit_per_mile = (
        _round(revenue_per_mile - cost_per_mile, 3)
        if revenue_per_mile is not None and cost_per_mile is not None
        else None
    )

    return {
        "added_p_and_l_ops": _round(added_p_and_l_ops),
        "cost_per_mile": cost_per_mile,
        "driver_pay": _round(driver_pay),
        "fleet_maintenance": _round(fleet_maintenance),
        "fuel": _round(fuel),
        "gross_profit": gross_profit,
        "miles": _round(miles, 1),
        "month": month,
        "other_ops": _round(other_ops),
        "payroll": _round(payroll),
        "profit_per_mile": profit_per_mile,
        "prior_cost": _round(prior_cost),
        "revenue": _round(revenue) if revenue is not None else None,
        "revenue_per_mile": revenue_per_mile,
        "total_cost": _round(total_cost),
    }


def _row_in_scope(row: Mapping[str, Any], date_value: str | None) -> bool:
    if not date_value:
        return True
    cutoff_month = str(date_value)[:7]
    return not MONTH_PATTERN.match(cutoff_month) or str(row["month"]) <= cutoff_month


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "added_p_and_l_ops": 0.0,
        "driver_pay": 0.0,
        "fleet_maintenance": 0.0,
        "fuel": 0.0,
        "miles": 0.0,
        "other_ops": 0.0,
        "payroll": 0.0,
        "prior_cost": 0.0,
        "revenue": 0.0,
        "total_cost": 0.0,
    }
    has_revenue = False
    for row in rows:
        for key in totals:
            if key == "revenue" and row.get(key) is None:
                continue
            totals[key] += float(row.get(key) or 0)
        has_revenue = has_revenue or row.get("revenue") is not None

    summary = {
        key: _round(value, 1 if key == "miles" else 2)
        for key, value in totals.items()
    }
    if not has_revenue:
        summary["revenue"] = None
    summary["gross_profit"] = _round(totals["revenue"] - totals["total_cost"]) if has_revenue else None
    summary["cost_per_mile"] = _ratio(totals["total_cost"], totals["miles"])
    summary["revenue_per_mile"] = _ratio(totals["revenue"], totals["miles"]) if has_revenue else None
    summary["profit_per_mile"] = (
        _round(summary["revenue_per_mile"] - summary["cost_per_mile"], 3)
        if summary["revenue_per_mile"] is not None and summary["cost_per_mile"] is not None
        else None
    )
    return summary


def get_k1l_operating_kpi_snapshot(
    *,
    date_value: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    try:
        config = _config_from_env(env)
        raw_rows, revenue_source, revenue_status = _merge_powerbi_revenue(
            config["monthly_rows"],
            config=config["powerbi"],
            enabled=config["revenue_source"] == POWERBI_REVENUE_SOURCE,
        )
        monthly = sorted(
            (
                row
                for row in (
                    normalize_k1l_operating_month(raw_row)
                    for raw_row in raw_rows
                )
                if _row_in_scope(row, date_value)
            ),
            key=lambda item: item["month"],
        )

        if not monthly:
            return {
                "entity": config["entity"],
                "generated_at": _now_iso(),
                "projection_mode": "read_only",
                "revenue_source": revenue_source,
                "revenue_source_status": revenue_status,
                "status": "not_configured",
                "summary": None,
            }

        return {
            "as_of_date": config["as_of_date"] or None,
            "entity": config["entity"],
            "excluded_accounts": config["excluded_accounts"],
            "generated_at": _now_iso(),
            "method": config["method"],
            "monthly": monthly,
            "projection_mode": "read_only",
            "revenue_source": revenue_source,
            "revenue_source_status": revenue_status,
            "source": config["source"],
            "status": "configured",
            "summary": _summarize(monthly),
        }
    except Exception as exc:
        return {
            "entity": DEFAULT_ENTITY,
            "error": str(exc),
            "generated_at": _now_iso(),
            "projection_mode": "read_only",
            "status": "configuration_error",
            "summary": None,
        }
