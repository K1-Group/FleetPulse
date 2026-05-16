"""Read-only K1 Logistics operating-cost KPI snapshot.

This lightweight projection is for first-screen dashboard cards. It reads a
pre-approved monthly cost stack from environment configuration and does not
mutate Xcelerator, Geotab, QuickBooks, AtoB, or Power BI.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Mapping


DEFAULT_ENTITY = "K1 Logistics Inc"
DEFAULT_SOURCE = "QBO K1 Logistics P&L + Xcelerator driver pay + AtoB fuel + Geotab miles"
DEFAULT_METHOD = (
    "driver_pay + fuel + amex_fleet_maintenance + "
    "qbo_p_and_l_operating_expenses_excluding_repairs_maintenance"
)
MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")


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
        "source": _read_string(
            parsed_json.get("source") or env.get("K1L_OPERATING_COST_SOURCE"),
            DEFAULT_SOURCE,
        ),
    }


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

    return {
        "added_p_and_l_ops": _round(added_p_and_l_ops),
        "cost_per_mile": _round(total_cost / miles, 3) if miles > 0 else None,
        "driver_pay": _round(driver_pay),
        "fleet_maintenance": _round(fleet_maintenance),
        "fuel": _round(fuel),
        "miles": _round(miles, 1),
        "month": month,
        "other_ops": _round(other_ops),
        "payroll": _round(payroll),
        "prior_cost": _round(prior_cost),
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
        "total_cost": 0.0,
    }
    for row in rows:
        for key in totals:
            totals[key] += float(row.get(key) or 0)

    summary = {
        key: _round(value, 1 if key == "miles" else 2)
        for key, value in totals.items()
    }
    summary["cost_per_mile"] = _round(totals["total_cost"] / totals["miles"], 3) if totals["miles"] > 0 else None
    return summary


def get_k1l_operating_kpi_snapshot(
    *,
    date_value: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    try:
        config = _config_from_env(env)
        monthly = sorted(
            (
                row
                for row in (
                    normalize_k1l_operating_month(raw_row)
                    for raw_row in config["monthly_rows"]
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
