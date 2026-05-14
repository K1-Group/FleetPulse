"""Read-only operating cost rollups for FleetPulse.

This service joins cost evidence without changing any source system:

- Geotab Data Connector owns miles and hours.
- AtoB exports own fuel card spend evidence.
- Xcelerator ReviewOrders owns driver pay.
- QuickBooks Online owns insurance and other company expenses.
"""

from __future__ import annotations

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

from services.atob_fuel_expense_service import AtoBFuelExpenseStateStore
from services.lane_stability_service import (
    LaneStabilityConfig,
    get_lane_stability_snapshot,
)


GEOTAB_AUTHORITY = "K1 Logistics Inc / Geotab Data Connector"
ATOB_AUTHORITY = "AtoB manual fuel expense export"
XCELERATOR_AUTHORITY = "K1 Group LLC / Xcelerator"
QBO_AUTHORITY = "K1 Group LLC / QuickBooks Online"
OPERATING_COST_AUTHORITY = (
    "Geotab miles/hours + AtoB fuel + Xcelerator driver pay + QBO expenses"
)
KM_TO_MILES = 0.621371


@dataclass(frozen=True)
class QboExpenseFeedConfig:
    """Runtime settings for a read-only QBO expense projection."""

    url: str = ""
    path: str = ""
    api_key: str = ""
    api_key_header: str = "X-FleetPulse-QBO-Key"
    timeout_seconds: float = 30.0
    insurance_patterns: tuple[str, ...] = ("insurance",)
    excluded_patterns: tuple[str, ...] = (
        "accounts receivable",
        "atob",
        "carrier",
        "cogs",
        "contractor",
        "cost of goods sold",
        "diesel",
        "driver pay",
        "driver settlement",
        "factoring",
        "fuel",
        "freight in",
        "income",
        "payroll",
        "revenue",
        "sales",
        "wages",
    )

    @classmethod
    def from_env(cls) -> "QboExpenseFeedConfig":
        return cls(
            url=(
                os.getenv("FLEETPULSE_QBO_EXPENSE_FEED_URL", "").strip()
                or os.getenv("FLEETPULSE_QBO_FINANCIAL_FEED_URL", "").strip()
            ),
            path=(
                os.getenv("FLEETPULSE_QBO_EXPENSE_FEED_PATH", "").strip()
                or os.getenv("FLEETPULSE_QBO_FINANCIAL_FEED_PATH", "").strip()
            ),
            api_key=os.getenv("FLEETPULSE_QBO_EXPENSE_FEED_API_KEY", "").strip(),
            api_key_header=(
                os.getenv(
                    "FLEETPULSE_QBO_EXPENSE_FEED_API_KEY_HEADER",
                    "X-FleetPulse-QBO-Key",
                ).strip()
                or "X-FleetPulse-QBO-Key"
            ),
            timeout_seconds=_float_env("FLEETPULSE_QBO_EXPENSE_TIMEOUT_SECONDS", 30.0),
            insurance_patterns=_csv_env(
                "FLEETPULSE_QBO_INSURANCE_ACCOUNT_PATTERNS",
                "insurance",
            ),
            excluded_patterns=_csv_env(
                "FLEETPULSE_QBO_EXCLUDED_ACCOUNT_PATTERNS",
                (
                    "accounts receivable,atob,diesel,driver pay,driver settlement,"
                    "carrier,cogs,contractor,cost of goods sold,factoring,fuel,"
                    "freight in,income,payroll,revenue,sales,wages"
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
        "driver_pay": 0.0,
        "insurance_cost": 0.0,
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


async def _fetch_vehicle_kpi_rows(start: date, end: date) -> list[dict[str, Any]]:
    from routers import data_connector

    return await data_connector._odata_get(  # noqa: SLF001 - shared internal OData helper.
        "VehicleKpi_Daily",
        search=f"from_{start.isoformat()}_to_{end.isoformat()}",
        top=5000,
    )


async def _geotab_weekly_metrics(
    weeks: list[tuple[date, date]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    row_count = 0
    failures: list[str] = []

    for start, end in weeks:
        key = _week_key(start)
        bucket = metrics.setdefault(key, _empty_week(start, end))
        try:
            rows = await _fetch_vehicle_kpi_rows(start, end)
        except Exception as exc:  # pragma: no cover - exact upstream exception varies.
            failures.append(f"{start.isoformat()}..{end.isoformat()}: {type(exc).__name__}")
            continue

        row_count += len(rows)
        for row in rows:
            distance_km = _number(
                _find_value(row, ("Distance_Km", "GPS_Distance_Km", "TotalDistance_Km"))
            )
            drive_hours = _number(_find_value(row, ("DriveDuration_Seconds",))) / 3600
            drive_hours += _number(_find_value(row, ("TotalDriveTime_Hours",)))
            idle_hours = _number(_find_value(row, ("IdleDuration_Seconds",))) / 3600
            idle_hours += _number(_find_value(row, ("TotalIdleTime_Hours",)))
            bucket["miles"] += distance_km * KM_TO_MILES
            bucket["drive_hours"] += drive_hours
            bucket["idle_hours"] += idle_hours
            bucket["trips"] += int(_number(_find_value(row, ("Trip_Count", "TotalTrips"))))

    for bucket in metrics.values():
        bucket["miles"] = round(bucket["miles"], 2)
        bucket["drive_hours"] = round(bucket["drive_hours"], 2)
        bucket["idle_hours"] = round(bucket["idle_hours"], 2)
        bucket["operating_hours"] = round(bucket["drive_hours"] + bucket["idle_hours"], 2)

    if row_count:
        return metrics, _source("healthy", GEOTAB_AUTHORITY, row_count=row_count)
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


def _xcelerator_driver_pay_by_week(
    start: date,
    end: date,
    *,
    config: LaneStabilityConfig | None = None,
) -> tuple[dict[str, float], dict[str, Any]]:
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


def _load_qbo_rows(config: QboExpenseFeedConfig) -> list[dict[str, Any]]:
    if config.url:
        headers = {"Accept": "application/json,text/csv"}
        if config.api_key:
            headers[config.api_key_header] = config.api_key
        with httpx.Client(timeout=config.timeout_seconds) as client:
            response = client.get(config.url, headers=headers)
        response.raise_for_status()
        return _coerce_rows(response.text, response.headers.get("content-type", ""))
    if config.path:
        return _coerce_rows(Path(config.path).read_text(encoding="utf-8-sig"), "")
    return []


def _coerce_rows(text: str, content_type: str) -> list[dict[str, Any]]:
    stripped = text.lstrip("\ufeff").strip()
    if not stripped:
        return []
    if "json" in content_type or stripped[:1] in {"[", "{"}:
        payload = json.loads(stripped)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("rows", "value", "expenses", "data", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [payload]
    sample = stripped[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in sample else csv.excel
    return [
        dict(row)
        for row in csv.DictReader(io.StringIO(stripped), dialect=dialect)
        if any(str(value or "").strip() for value in row.values())
    ]


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
        ),
    )
    return abs(_number(amount))


def _qbo_row_bucket(row: dict[str, Any], config: QboExpenseFeedConfig) -> str | None:
    haystack = " ".join(
        str(
            _find_value(
                row,
                (
                    "Account",
                    "Account Name",
                    "Category",
                    "Expense Category",
                    "Name",
                    "Memo",
                    "Description",
                    "Transaction Type",
                ),
            )
            or ""
        )
        for _ in range(1)
    ).casefold()
    if not haystack:
        haystack = " ".join(str(value or "") for value in row.values()).casefold()
    if any(pattern.casefold() in haystack for pattern in config.excluded_patterns):
        return None
    if any(pattern.casefold() in haystack for pattern in config.insurance_patterns):
        return "insurance"
    return "other"


def _qbo_weekly_costs(
    start: date,
    end: date,
    *,
    config: QboExpenseFeedConfig | None = None,
) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    config = config or QboExpenseFeedConfig.from_env()
    if not config.configured:
        return {}, _source(
            "awaiting_feed",
            QBO_AUTHORITY,
            message="QBO expense feed URL/path is not configured.",
        )

    rows = _load_qbo_rows(config)
    weekly: dict[str, dict[str, float]] = {}
    row_count = 0
    for row in rows:
        day = _qbo_row_day(row)
        if day is None or not (start <= day <= end):
            continue
        bucket_name = _qbo_row_bucket(row, config)
        if bucket_name is None:
            continue
        week = weekly.setdefault(_week_key(day), {"insurance": 0.0, "other": 0.0})
        week[bucket_name] += _qbo_row_amount(row)
        row_count += 1

    return (
        {
            key: {"insurance": _money(value["insurance"]), "other": _money(value["other"])}
            for key, value in weekly.items()
        },
        _source("healthy", QBO_AUTHORITY, row_count=row_count),
    )


def _component_sources_complete(sources: dict[str, dict[str, Any]]) -> bool:
    return all(
        sources[name]["status"] == "healthy"
        for name in ("telemetry", "fuel", "driver_pay", "qbo_expenses")
    )


def _finalize_week(row: dict[str, Any], *, complete: bool) -> dict[str, Any]:
    known_cost = (
        float(row["fuel_cost"])
        + float(row["driver_pay"])
        + float(row["insurance_cost"])
        + float(row["other_expense_cost"])
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
        "driver_pay": sum(float(row["driver_pay"]) for row in weekly),
        "insurance_cost": sum(float(row["insurance_cost"]) for row in weekly),
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
        "driver_pay": _money(totals["driver_pay"]),
        "insurance_cost": _money(totals["insurance_cost"]),
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
) -> dict[str, Any]:
    """Return weekly operating-cost rows for dashboard and Power BI use."""

    period_start, period_end = _resolve_window(days, start, end)
    weeks = _week_windows(period_start, period_end)
    weekly = {_week_key(start_date): _empty_week(start_date, end_date) for start_date, end_date in weeks}

    geotab_metrics, telemetry_source = await _geotab_weekly_metrics(weeks)
    fuel_by_week, fuel_source = _atob_weekly_costs(period_start, period_end, store=atob_store)
    driver_pay_by_week, driver_source = _xcelerator_driver_pay_by_week(
        period_start,
        period_end,
        config=lane_config,
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
        weekly.setdefault(key, _empty_week(date.fromisoformat(key), date.fromisoformat(key)))["fuel_cost"] = value
    for key, value in driver_pay_by_week.items():
        weekly.setdefault(key, _empty_week(date.fromisoformat(key), date.fromisoformat(key)))["driver_pay"] = value
    for key, value in qbo_by_week.items():
        bucket = weekly.setdefault(key, _empty_week(date.fromisoformat(key), date.fromisoformat(key)))
        bucket["insurance_cost"] = value["insurance"]
        bucket["other_expense_cost"] = value["other"]

    sources = {
        "telemetry": telemetry_source,
        "fuel": fuel_source,
        "driver_pay": driver_source,
        "qbo_expenses": qbo_source,
    }
    complete = _component_sources_complete(sources)
    rows = [_finalize_week(row, complete=complete) for _, row in sorted(weekly.items())]

    unresolved_sources = [
        name
        for name, source in sources.items()
        if source.get("status") != "healthy"
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
