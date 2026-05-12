"""Lane stability scoring for read-only Xcelerator ReviewOrders data."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any

import httpx

from integrations.xcelerator.review_orders_feed import (
    ReviewOrdersFeedConfig,
    load_review_orders_rows,
)


DEFAULT_EXCLUDED_SCORING_SERVICES = "ATL-ShipBob"
DEFAULT_EXCLUDED_SCORING_REF_PATTERNS = "pay ticket,route ticket,tonu,service-only"


@dataclass(frozen=True)
class LaneStabilityConfig:
    """Runtime settings for lane stability scoring."""

    order_feed: ReviewOrdersFeedConfig
    baseline_feed: ReviewOrdersFeedConfig
    payload_url: str = ""
    payload_path: str = ""
    baseline_payload_url: str = ""
    baseline_payload_path: str = ""
    excluded_scoring_services: tuple[str, ...] = ()
    excluded_scoring_ref_patterns: tuple[str, ...] = ()
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "LaneStabilityConfig":
        timeout_seconds = _float_env("FLEETPULSE_LANE_STABILITY_TIMEOUT_SECONDS", 30.0)
        return cls(
            order_feed=ReviewOrdersFeedConfig.from_env("FLEETPULSE_LANE_STABILITY"),
            baseline_feed=ReviewOrdersFeedConfig.from_env("FLEETPULSE_LANE_STABILITY_BASELINE"),
            payload_url=os.getenv("FLEETPULSE_LANE_STABILITY_PAYLOAD_URL", "").strip(),
            payload_path=os.getenv("FLEETPULSE_LANE_STABILITY_PAYLOAD_PATH", "").strip(),
            baseline_payload_url=os.getenv("FLEETPULSE_LANE_STABILITY_BASELINE_PAYLOAD_URL", "").strip(),
            baseline_payload_path=os.getenv("FLEETPULSE_LANE_STABILITY_BASELINE_PAYLOAD_PATH", "").strip(),
            excluded_scoring_services=_csv_env(
                "FLEETPULSE_LANE_STABILITY_EXCLUDED_SCORING_SERVICES",
                DEFAULT_EXCLUDED_SCORING_SERVICES,
            ),
            excluded_scoring_ref_patterns=_csv_env(
                "FLEETPULSE_LANE_STABILITY_EXCLUDED_SCORING_REF_PATTERNS",
                DEFAULT_EXCLUDED_SCORING_REF_PATTERNS,
            ),
            timeout_seconds=timeout_seconds,
        )

    @property
    def configured(self) -> bool:
        return bool(self.payload_url or self.payload_path or self.order_feed.configured)


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(name, default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_value(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    lower_aliases = {alias.casefold() for alias in aliases}
    normalized_aliases = {_normalize_key(alias) for alias in aliases}
    for key, value in row.items():
        key_text = str(key)
        if key_text.casefold() in lower_aliases or _normalize_key(key_text) in normalized_aliases:
            return value
    return None


def _normalize_key(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).strip().replace("$", "").replace(",", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _date_value(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        # Excel serial date, using the common 1899-12-30 epoch.
        if value > 20000:
            return date(1899, 12, 30) + timedelta(days=int(value))
        return None

    raw = str(value).strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%m-%d-%y"):
        try:
            return datetime.strptime(raw.split()[0], fmt).date()
        except ValueError:
            continue
    return None


def _row_date(row: dict[str, Any]) -> date | None:
    return _date_value(
        _find_value(
            row,
            (
                "[P]From Date",
                "From Date",
                "from_date",
                "pickup_date",
                "Pickup Date",
                "Order Date",
                "oDate",
                "ODate",
                "ScheduledUTC",
                "date",
            ),
        )
    )


def _service(row: dict[str, Any]) -> str:
    return _text(_find_value(row, ("Service", "service", "Service Type", "service_type", "ServiceName", "service_name")))


def _lane(row: dict[str, Any]) -> str:
    return _text(
        _find_value(
            row,
            (
                "Ref#",
                "Ref #",
                "Reference",
                "Lane",
                "lane",
                "lane_name",
                "ClientRefNo",
                "client_ref_no",
            ),
        )
    )


def _driver(row: dict[str, Any]) -> str:
    return _text(_find_value(row, ("DriverNo", "Driver No", "driver_no", "driver", "Driver")), "UNASSIGNED")


def _route(row: dict[str, Any]) -> str:
    return _text(_find_value(row, ("RouteNo", "Route No", "route_no", "route", "Route")), "UNASSIGNED")


def _revenue(row: dict[str, Any]) -> float:
    return _number(_find_value(row, ("Grand Total", "grand_total", "GrandTotal", "revenue")))


def _gross_margin(row: dict[str, Any]) -> float:
    return _number(_find_value(row, ("Gross Margin($)", "Gross Margin", "gross_margin", "gm")))


def _driver_pay(row: dict[str, Any]) -> float:
    return _number(_find_value(row, ("Driver Pay", "driver_pay", "DriverPay")))


def _order_charge(row: dict[str, Any]) -> float:
    return _number(_find_value(row, ("Order Charge", "order_charge", "OrderCharge")))


def _is_footer_row(row: dict[str, Any]) -> bool:
    service = _service(row)
    lane = _lane(row)
    driver = _text(_find_value(row, ("DriverNo", "Driver No", "driver_no", "driver", "Driver")))
    route = _text(_find_value(row, ("RouteNo", "Route No", "route_no", "route", "Route")))
    has_money = any((_revenue(row), _gross_margin(row), _driver_pay(row), _order_charge(row)))
    label_text = " ".join(str(value) for value in row.values() if isinstance(value, str)).casefold()
    explicit_total = "total" in label_text and not service and not lane
    blank_key_total = not service and not lane and not driver and not route and has_money
    return bool(explicit_total or blank_key_total)


def _filter_by_window(rows: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for row in rows:
        row_day = _row_date(row)
        if row_day is None or start <= row_day <= end:
            filtered.append(row)
    return filtered


def _window_for_rows(rows: list[dict[str, Any]], days: int, start: date | None, end: date | None) -> tuple[date, date]:
    row_dates = [row_day for row in rows if (row_day := _row_date(row)) is not None]
    window_end = end or (max(row_dates) if row_dates else datetime.now(timezone.utc).date())
    window_start = start or (window_end - timedelta(days=max(days, 1) - 1))
    return window_start, window_end


def _status(stable_cov_pct: float) -> str:
    if stable_cov_pct >= 0.8:
        return "Stable"
    if stable_cov_pct >= 0.7:
        return "Watch"
    if stable_cov_pct >= 0.5:
        return "At Risk"
    return "Critical"


def _status_rank(status: str) -> int:
    return {"Stable": 1, "Watch": 2, "At Risk": 3, "Critical": 4}.get(status, 0)


def _pct(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _money(value: float) -> float:
    return round(value, 2)


def _top(counter: Counter[str]) -> tuple[str, int]:
    if not counter:
        return "UNASSIGNED", 0
    return counter.most_common(1)[0]


def _routes_used(counter: Counter[str]) -> str:
    return ", ".join(f"{route}:{count}" for route, count in counter.most_common())


def _is_scoring_row(row: dict[str, Any], config: LaneStabilityConfig) -> bool:
    if _is_footer_row(row):
        return False
    service = _service(row)
    lane = _lane(row)
    if not service or not lane:
        return False

    excluded_services = {service_name.casefold() for service_name in config.excluded_scoring_services}
    if service.casefold() in excluded_services:
        return False

    lane_casefold = lane.casefold()
    return not any(pattern.casefold() in lane_casefold for pattern in config.excluded_scoring_ref_patterns)


def _load_payload(path: str, url: str, timeout_seconds: float) -> dict[str, Any] | None:
    if url:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(url, headers={"Accept": "application/json"})
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    if path:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    return None


def _normalize_payload_snapshot(payload: dict[str, Any], feed_status: str = "healthy") -> dict[str, Any]:
    period_start = str(payload.get("period_start") or "")
    period_end = str(payload.get("period_end") or "")
    company = dict(payload.get("company_kpis") or {})
    company.setdefault("period_start", period_start)
    company.setdefault("period_end", period_end)
    company.setdefault("feed_status", feed_status)
    company.setdefault("source_authority", "K1 Group LLC / Xcelerator")
    company.setdefault("projection_mode", "read_only")
    company.setdefault("generated_at", payload.get("generated_at") or _now_iso())

    trend = payload.get("trend") or {}
    trend_rows: list[dict[str, Any]] = []
    if isinstance(trend, dict):
        for trend_type in ("improving", "degrading", "flat", "new", "dropped"):
            for item in trend.get(trend_type, []) or []:
                row = dict(item)
                row["trend_type"] = trend_type
                row.setdefault("period_start", period_start)
                row.setdefault("period_end", period_end)
                trend_rows.append(row)

    return {
        "period_start": period_start,
        "period_end": period_end,
        "generated_at": payload.get("generated_at") or _now_iso(),
        "feed_status": feed_status,
        "company_kpis": company,
        "by_service": list(payload.get("by_service") or []),
        "lanes": list(payload.get("lanes") or []),
        "daily": list(payload.get("daily") or []),
        "routes": list(payload.get("routes") or payload.get("route_breakdown") or []),
        "trend": trend_rows,
        "row_counts": {
            "by_service": len(payload.get("by_service") or []),
            "lanes": len(payload.get("lanes") or []),
            "daily": len(payload.get("daily") or []),
            "routes": len(payload.get("routes") or payload.get("route_breakdown") or []),
            "trend": len(trend_rows),
        },
    }


def _empty_snapshot(days: int, feed_status: str, message: str = "") -> dict[str, Any]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=max(days, 1) - 1)
    company = {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "generated_at": _now_iso(),
        "feed_status": feed_status,
        "feed_message": message,
        "source_authority": "K1 Group LLC / Xcelerator",
        "projection_mode": "read_only",
        "total_orders": 0,
        "billed_orders": 0,
        "total_revenue": 0.0,
        "total_revenue_source": "no_feed",
        "total_gm": 0.0,
        "gm_pct": 0.0,
        "total_driver_pay": 0.0,
        "team_subset_revenue": 0.0,
        "team_subset_gm": 0.0,
        "weighted_stable_cov_pct": 0.0,
        "baseline_weighted_stable_cov_pct": 0.0,
        "delta_vs_baseline_pct": 0.0,
        "total_lanes": 0,
        "critical": 0,
        "at_risk": 0,
        "watch": 0,
        "stable": 0,
        "cross_route_lanes": 0,
    }
    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "generated_at": company["generated_at"],
        "feed_status": feed_status,
        "company_kpis": company,
        "by_service": [],
        "lanes": [],
        "daily": [],
        "routes": [],
        "trend": [],
        "row_counts": {"by_service": 0, "lanes": 0, "daily": 0, "routes": 0, "trend": 0},
    }


def _score_rows(
    rows: list[dict[str, Any]],
    config: LaneStabilityConfig,
    *,
    days: int,
    start: date | None = None,
    end: date | None = None,
    baseline_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    period_start, period_end = _window_for_rows(rows, days, start, end)
    current_rows = _filter_by_window(rows, period_start, period_end)
    data_rows = [row for row in current_rows if not _is_footer_row(row)]
    footer_rows = [row for row in current_rows if _is_footer_row(row)]
    scoring_rows = [row for row in data_rows if _is_scoring_row(row, config)]

    lanes = _lane_rows(scoring_rows)
    by_service = _service_rows(lanes)
    daily = _daily_rows(scoring_rows)
    routes = _route_rows(scoring_rows, lanes)

    total_revenue_source = "row_sum"
    if footer_rows:
        total_revenue_source = "xcelerator_footer"
        footer = footer_rows[-1]
        total_revenue = _revenue(footer)
        total_gm = _gross_margin(footer)
        total_driver_pay = _driver_pay(footer)
    else:
        total_revenue = sum(_revenue(row) for row in data_rows)
        total_gm = sum(_gross_margin(row) for row in data_rows)
        total_driver_pay = sum(_driver_pay(row) for row in data_rows)

    status_counts = Counter(row["status"] for row in lanes)
    stable_runs = sum(int(row["stable_runs"]) for row in lanes)
    team_subset_orders = sum(int(row["orders"]) for row in lanes)
    baseline_metric = 0.0
    trend_rows: list[dict[str, Any]] = []
    if baseline_rows:
        baseline_snapshot = _score_rows(
            baseline_rows,
            config,
            days=90,
            start=None,
            end=None,
            baseline_rows=None,
        )
        baseline_metric = float(baseline_snapshot["company_kpis"].get("weighted_stable_cov_pct") or 0)
        trend_rows = _trend_rows(baseline_snapshot["lanes"], lanes, period_start, period_end)

    company_kpis = {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "generated_at": _now_iso(),
        "feed_status": "healthy",
        "source_authority": "K1 Group LLC / Xcelerator",
        "projection_mode": "read_only",
        "total_orders": len(data_rows),
        "billed_orders": sum(1 for row in data_rows if _revenue(row) != 0),
        "total_revenue": _money(total_revenue),
        "total_revenue_source": total_revenue_source,
        "total_gm": _money(total_gm),
        "gm_pct": _pct(total_gm, total_revenue),
        "total_driver_pay": _money(total_driver_pay),
        "team_subset_revenue": _money(sum(float(row["revenue"]) for row in lanes)),
        "team_subset_gm": _money(sum(float(row["gm"]) for row in lanes)),
        "weighted_stable_cov_pct": _pct(stable_runs, team_subset_orders),
        "baseline_weighted_stable_cov_pct": baseline_metric,
        "delta_vs_baseline_pct": round(_pct(stable_runs, team_subset_orders) - baseline_metric, 4),
        "total_lanes": len(lanes),
        "critical": status_counts["Critical"],
        "at_risk": status_counts["At Risk"],
        "watch": status_counts["Watch"],
        "stable": status_counts["Stable"],
        "cross_route_lanes": sum(1 for row in lanes if row["cross_route"]),
    }

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "generated_at": company_kpis["generated_at"],
        "feed_status": "healthy",
        "company_kpis": company_kpis,
        "by_service": by_service,
        "lanes": lanes,
        "daily": daily,
        "routes": routes,
        "trend": trend_rows,
        "row_counts": {
            "by_service": len(by_service),
            "lanes": len(lanes),
            "daily": len(daily),
            "routes": len(routes),
            "trend": len(trend_rows),
        },
    }


def _lane_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(_service(row), _lane(row))].append(row)

    lane_rows: list[dict[str, Any]] = []
    for (service, lane), lane_group in grouped.items():
        driver_counter = Counter(_driver(row) for row in lane_group)
        route_counter = Counter(_route(row) for row in lane_group)
        stable_driver, stable_runs = _top(driver_counter)
        primary_route, primary_route_runs = _top(route_counter)
        orders = len(lane_group)
        revenue = sum(_revenue(row) for row in lane_group)
        gm = sum(_gross_margin(row) for row in lane_group)
        driver_pay = sum(_driver_pay(row) for row in lane_group)
        stable_cov_pct = _pct(stable_runs, orders)
        status = _status(stable_cov_pct)
        row = {
            "service": service,
            "lane": lane,
            "status": status,
            "status_rank": _status_rank(status),
            "orders": orders,
            "unique_drivers": len(driver_counter),
            "stable_driver": stable_driver,
            "stable_runs": stable_runs,
            "stable_cov_pct": stable_cov_pct,
            "swaps": max(len(driver_counter) - 1, 0),
            "swap_rate_pct": _pct(max(len(driver_counter) - 1, 0), max(orders - 1, 1)),
            "revenue": _money(revenue),
            "gm": _money(gm),
            "gm_pct": _pct(gm, revenue),
            "driver_pay": _money(driver_pay),
            "num_routes": len(route_counter),
            "primary_route": primary_route,
            "primary_route_pct": _pct(primary_route_runs, orders),
            "cross_route": len(route_counter) > 1,
            "routes_used": _routes_used(route_counter),
        }
        lane_rows.append(row)

    return sorted(lane_rows, key=lambda row: (str(row["service"]), float(row["stable_cov_pct"]), str(row["lane"])))


def _service_rows(lanes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for lane in lanes:
        grouped[str(lane["service"])].append(lane)

    service_rows: list[dict[str, Any]] = []
    for service, service_lanes in grouped.items():
        orders = sum(int(row["orders"]) for row in service_lanes)
        stable_runs = sum(int(row["stable_runs"]) for row in service_lanes)
        revenue = sum(float(row["revenue"]) for row in service_lanes)
        gm = sum(float(row["gm"]) for row in service_lanes)
        counts = Counter(str(row["status"]) for row in service_lanes)
        service_rows.append(
            {
                "service": service,
                "lanes": len(service_lanes),
                "critical": counts["Critical"],
                "at_risk": counts["At Risk"],
                "watch": counts["Watch"],
                "stable": counts["Stable"],
                "cross_route": sum(1 for row in service_lanes if row["cross_route"]),
                "orders": orders,
                "revenue": _money(revenue),
                "gm": _money(gm),
                "gm_pct": _pct(gm, revenue),
                "weighted_stable_cov_pct": _pct(stable_runs, orders),
            }
        )
    return sorted(service_rows, key=lambda row: (str(row["service"])))


def _daily_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        row_day = _row_date(row)
        if row_day:
            grouped[row_day].append(row)

    daily_rows: list[dict[str, Any]] = []
    for row_day, day_rows in sorted(grouped.items()):
        lanes = _lane_rows(day_rows)
        stable_runs = sum(int(row["stable_runs"]) for row in lanes)
        orders = sum(int(row["orders"]) for row in lanes)
        daily_rows.append(
            {
                "date": row_day.isoformat(),
                "orders": orders,
                "active_lanes": len(lanes),
                "active_drivers": len({_driver(row) for row in day_rows}),
                "revenue": _money(sum(_revenue(row) for row in day_rows)),
                "gm": _money(sum(_gross_margin(row) for row in day_rows)),
                "driver_pay": _money(sum(_driver_pay(row) for row in day_rows)),
                "daily_stable_cov_pct": _pct(stable_runs, orders),
            }
        )
    return daily_rows


def _route_rows(rows: list[dict[str, Any]], lanes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lane_lookup = {(str(row["service"]), str(row["lane"])): row for row in lanes}
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(_service(row), _lane(row), _route(row))].append(row)

    route_rows: list[dict[str, Any]] = []
    for (service, lane, route), route_group in grouped.items():
        lane_row = lane_lookup.get((service, lane), {})
        driver_counter = Counter(_driver(row) for row in route_group)
        primary_driver, primary_driver_runs = _top(driver_counter)
        orders = len(route_group)
        lane_orders = int(lane_row.get("orders") or orders)
        revenue = sum(_revenue(row) for row in route_group)
        gm = sum(_gross_margin(row) for row in route_group)
        route_rows.append(
            {
                "service": service,
                "lane": lane,
                "route": route,
                "orders": orders,
                "route_pct_of_lane": _pct(orders, lane_orders),
                "primary_driver": primary_driver,
                "primary_driver_runs": primary_driver_runs,
                "route_stable_cov_pct": _pct(primary_driver_runs, orders),
                "lane_stable_cov_pct": float(lane_row.get("stable_cov_pct") or 0),
                "lane_status": lane_row.get("status") or "",
                "lane_status_rank": int(lane_row.get("status_rank") or 0),
                "revenue": _money(revenue),
                "gm": _money(gm),
                "gm_pct": _pct(gm, revenue),
            }
        )
    return sorted(
        route_rows,
        key=lambda row: (str(row["service"]), str(row["lane"]), -int(row["orders"]), str(row["route"])),
    )


def _trend_rows(
    baseline_lanes: list[dict[str, Any]],
    current_lanes: list[dict[str, Any]],
    period_start: date,
    period_end: date,
) -> list[dict[str, Any]]:
    baseline = {(str(row["service"]), str(row["lane"])): row for row in baseline_lanes}
    current = {(str(row["service"]), str(row["lane"])): row for row in current_lanes}
    rows: list[dict[str, Any]] = []
    all_keys = sorted(set(baseline) | set(current))
    for service, lane in all_keys:
        base = baseline.get((service, lane))
        cur = current.get((service, lane))
        base_cov = float(base.get("stable_cov_pct") or 0) if base else None
        cur_cov = float(cur.get("stable_cov_pct") or 0) if cur else None
        if base is None:
            trend_type = "new"
            delta = None
        elif cur is None:
            trend_type = "dropped"
            delta = None
        else:
            delta = round(cur_cov - base_cov, 4)
            if delta >= 0.05:
                trend_type = "improving"
            elif delta <= -0.05:
                trend_type = "degrading"
            else:
                trend_type = "flat"
        rows.append(
            {
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "service": service,
                "lane": lane,
                "trend_type": trend_type,
                "baseline_stable_cov_pct": base_cov,
                "current_stable_cov_pct": cur_cov,
                "delta_stable_cov_pct": delta,
                "baseline_status": base.get("status") if base else "",
                "current_status": cur.get("status") if cur else "",
                "current_revenue": float(cur.get("revenue") or 0) if cur else 0.0,
                "current_orders": int(cur.get("orders") or 0) if cur else 0,
                "current_num_routes": int(cur.get("num_routes") or 0) if cur else 0,
                "current_primary_route": cur.get("primary_route") if cur else "",
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            {"degrading": 0, "improving": 1, "new": 2, "flat": 3, "dropped": 4}.get(str(row["trend_type"]), 9),
            float(row.get("delta_stable_cov_pct") or 0),
            str(row["service"]),
            str(row["lane"]),
        ),
    )


def get_lane_stability_snapshot(
    days: int = 7,
    *,
    start: date | None = None,
    end: date | None = None,
    config: LaneStabilityConfig | None = None,
) -> dict[str, Any]:
    """Return a table-shaped lane stability snapshot for FleetPulse and Power BI."""

    config = config or LaneStabilityConfig.from_env()
    if not config.configured:
        return _empty_snapshot(days, "awaiting_feed", "Lane stability feed is not configured.")

    try:
        payload = _load_payload(config.payload_path, config.payload_url, config.timeout_seconds)
        if payload is not None:
            return _normalize_payload_snapshot(payload)

        rows = load_review_orders_rows(config.order_feed)
        baseline_rows = load_review_orders_rows(config.baseline_feed) if config.baseline_feed.configured else []
        baseline_payload = _load_payload(
            config.baseline_payload_path,
            config.baseline_payload_url,
            config.timeout_seconds,
        )
        if baseline_payload and not baseline_rows:
            # Existing scored payloads cannot rebuild route detail, but they can
            # still anchor lane-level trend if they contain lane rows.
            baseline_rows = []
        snapshot = _score_rows(rows, config, days=days, start=start, end=end, baseline_rows=baseline_rows)
        if baseline_payload and snapshot["trend"] == []:
            baseline_lanes = list(baseline_payload.get("lanes") or [])
            current_lanes = snapshot["lanes"]
            period_start = datetime.fromisoformat(snapshot["period_start"]).date()
            period_end = datetime.fromisoformat(snapshot["period_end"]).date()
            snapshot["trend"] = _trend_rows(baseline_lanes, current_lanes, period_start, period_end)
            snapshot["row_counts"]["trend"] = len(snapshot["trend"])
            baseline_company = baseline_payload.get("company_kpis") or {}
            baseline_metric = float(baseline_company.get("weighted_stable_cov_pct") or 0)
            snapshot["company_kpis"]["baseline_weighted_stable_cov_pct"] = baseline_metric
            snapshot["company_kpis"]["delta_vs_baseline_pct"] = round(
                float(snapshot["company_kpis"].get("weighted_stable_cov_pct") or 0) - baseline_metric,
                4,
            )
        return snapshot
    except Exception as exc:
        return _empty_snapshot(days, "unavailable", f"{type(exc).__name__}: {exc}")
