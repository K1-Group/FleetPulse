"""Fast read-only gross margin projection from Xcelerator ReviewOrders rows."""

from __future__ import annotations

import os
import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from integrations.xcelerator.review_orders_feed import (
    ReviewOrdersFeedConfig,
    load_review_orders_rows,
)


K1L_ENTITY = "K1 Logistics Inc"
K1G_ENTITY = "K1 Group LLC"
SOURCE_AUTHORITY = "K1 Group LLC / Xcelerator ReviewOrders"
PROJECTION_MODE = "read_only"

_CACHE: dict[str, Any] = {}
_REBUILD_LOCK = threading.Lock()
_REBUILD_STATUS: dict[str, Any] = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "message": "Gross margin summary rebuild has not run in this process.",
    "snapshot": None,
}


@dataclass(frozen=True)
class GrossMarginWindow:
    start: date
    end: date


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _default_start() -> date:
    configured = os.getenv("FLEETPULSE_GROSS_MARGIN_START_DATE", "").strip()
    parsed = _coerce_date(configured)
    if parsed:
        return parsed
    today = _today()
    return date(today.year, 1, 1)


def _resolve_window(start: str | date | datetime | None = None, end: str | date | datetime | None = None) -> GrossMarginWindow:
    window_end = _coerce_date(end) or _today()
    window_start = _coerce_date(start) or _default_start()
    if window_start > window_end:
        raise ValueError("start must be on or before end")
    return GrossMarginWindow(start=window_start, end=window_end)


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
    cleaned = text.replace("$", "").replace(",", "").replace("%", "")
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


def _row_day(row: dict[str, Any]) -> date | None:
    return _coerce_date(
        _find_value(
            row,
            (
                "[P]From Date",
                "PFrom Date",
                "From Date",
                "Order Date",
                "pickup_target_from",
                "date",
            ),
        )
    )


def _delivery_center(row: dict[str, Any]) -> str:
    return str(
        _find_value(
            row,
            ("Delivery Center", "DeliveryCenter", "delivery_center", "Delivery Center Name"),
        )
        or ""
    ).strip()


def _entity_from_delivery_center(value: Any) -> str | None:
    normalized = _normalize(value)
    if not normalized or "test" in normalized:
        return None
    if "k1logistics" in normalized:
        return K1L_ENTITY
    if "k1group" in normalized:
        return K1G_ENTITY
    return None


def _revenue(row: dict[str, Any]) -> float:
    return _number(
        _find_value(
            row,
            ("Grand Total", "GrandTotal", "grand_total", "grand_total_amount", "Revenue"),
        )
    )


def _driver_pay(row: dict[str, Any]) -> float:
    return _number(_find_value(row, ("Driver Pay", "DriverPay", "driver_pay", "driver_pay_amount")))


def _gross_margin(row: dict[str, Any]) -> tuple[float, str]:
    explicit = _find_value(row, ("Gross Margin($)", "Gross Margin", "gross_margin", "gm"))
    if explicit not in (None, ""):
        return _number(explicit), "xcelerator_gross_margin_field"
    return _revenue(row) - _driver_pay(row), "revenue_minus_driver_pay"


def _order_count(row: dict[str, Any]) -> int:
    explicit = _find_value(row, ("Orders", "OrderCount", "order_count"))
    if explicit not in (None, ""):
        return max(int(_number(explicit)), 0)
    return 1


def _week_key(day: date) -> str:
    return (day - timedelta(days=day.weekday())).isoformat()


def _month_key(day: date) -> str:
    return date(day.year, day.month, 1).isoformat()


def _money(value: float) -> float:
    return round(float(value or 0), 2)


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _empty_bucket(entity: str) -> dict[str, Any]:
    return {
        "entity": entity,
        "orders": 0,
        "revenue": 0.0,
        "driver_pay": 0.0,
        "gross_margin": 0.0,
        "gross_margin_pct": None,
    }


def _finish_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    revenue = float(bucket["revenue"] or 0)
    gross_margin = float(bucket["gross_margin"] or 0)
    return {
        **bucket,
        "revenue": _money(revenue),
        "driver_pay": _money(float(bucket["driver_pay"] or 0)),
        "gross_margin": _money(gross_margin),
        "gross_margin_pct": _ratio(gross_margin, revenue),
    }


def _feed_config() -> ReviewOrdersFeedConfig:
    config = ReviewOrdersFeedConfig.from_env("FLEETPULSE_XCELERATOR_GROSS_MARGIN")
    if config.configured:
        return config
    config = ReviewOrdersFeedConfig.from_env("FLEETPULSE_XCELERATOR_ENTITY_MARGIN")
    if config.configured:
        return config
    return ReviewOrdersFeedConfig.from_env("FLEETPULSE_LANE_STABILITY")


def _source_signature(config: ReviewOrdersFeedConfig) -> tuple[str, float | None, int | None]:
    if config.path:
        try:
            stat = Path(config.path).stat()
        except OSError:
            return (config.path, None, None)
        return (config.path, stat.st_mtime, stat.st_size)
    return (config.url, None, None)


def _summary_cache_path(config: ReviewOrdersFeedConfig) -> Path | None:
    configured = os.getenv("FLEETPULSE_XCELERATOR_GROSS_MARGIN_SUMMARY_PATH", "").strip()
    if configured:
        return Path(configured)
    if config.path:
        path = Path(config.path)
        return path.with_suffix(f".gross_margin_summary{path.suffix}")
    return None


def _request_rebuild_max_bytes() -> int:
    try:
        return max(int(os.getenv("FLEETPULSE_GROSS_MARGIN_REQUEST_REBUILD_MAX_BYTES", "8000000")), 0)
    except ValueError:
        return 8_000_000


def _should_skip_request_rebuild(config: ReviewOrdersFeedConfig, signature: tuple[str, float | None, int | None]) -> bool:
    if os.getenv("FLEETPULSE_GROSS_MARGIN_ALLOW_REQUEST_REBUILD", "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    if config.url:
        return True
    if not config.path:
        return False
    size = signature[2]
    return size is not None and size > _request_rebuild_max_bytes()


def _missing_summary_cache_payload(
    window: GrossMarginWindow,
    *,
    required_config: list[str],
    signature: tuple[str, float | None, int | None],
) -> dict[str, Any]:
    return {
        "status": "awaiting_feed",
        "source_authority": SOURCE_AUTHORITY,
        "projection_mode": PROJECTION_MODE,
        "period_start": window.start.isoformat(),
        "period_end": window.end.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "message": (
            "Xcelerator gross margin summary cache is missing. "
            "Large ReviewOrders files are not summarized inside dashboard requests."
        ),
        "required_config": [
            *required_config,
            "FLEETPULSE_XCELERATOR_GROSS_MARGIN_SUMMARY_PATH",
        ],
        "summary": _finish_bucket(_empty_bucket("K1 total")),
        "entities": [],
        "weekly": [],
        "monthly": [],
        "monthly_entities": [],
        "row_count": 0,
        "excluded_row_count": 0,
        "source_method": "summary_cache_missing",
        "last_updated": datetime.fromtimestamp(signature[1], tz=timezone.utc).isoformat()
        if signature[1]
        else None,
    }


def _load_summary_cache(
    cache_key: str,
    signature: tuple[str, float | None, int | None],
    *,
    config: ReviewOrdersFeedConfig,
) -> dict[str, Any] | None:
    path = _summary_cache_path(config)
    if not path or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("cache_key") != cache_key:
        return None
    if tuple(payload.get("signature") or ()) != signature:
        return None
    snapshot = payload.get("snapshot")
    if isinstance(snapshot, dict) and ("monthly" not in snapshot or "monthly_entities" not in snapshot):
        return None
    return snapshot if isinstance(snapshot, dict) else None


def _save_summary_cache(
    cache_key: str,
    signature: tuple[str, float | None, int | None],
    snapshot: dict[str, Any],
    *,
    config: ReviewOrdersFeedConfig,
) -> None:
    path = _summary_cache_path(config)
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(
            json.dumps(
                {
                    "cache_key": cache_key,
                    "signature": signature,
                    "snapshot": snapshot,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        tmp_path.replace(path)
    except OSError:
        return


def _cache_ttl_seconds() -> float:
    try:
        return max(float(os.getenv("FLEETPULSE_GROSS_MARGIN_CACHE_TTL_SECONDS", "300")), 1.0)
    except ValueError:
        return 300.0


def _cached_snapshot(cache_key: str, signature: tuple[str, float | None, int | None]) -> dict[str, Any] | None:
    cached = _CACHE.get(cache_key)
    if not cached:
        return None
    if cached.get("signature") != signature:
        return None
    if time.monotonic() - float(cached.get("cached_at", 0)) > _cache_ttl_seconds():
        return None
    return cached["payload"]


def _store_cache(cache_key: str, signature: tuple[str, float | None, int | None], payload: dict[str, Any]) -> dict[str, Any]:
    _CACHE[cache_key] = {
        "cached_at": time.monotonic(),
        "signature": signature,
        "payload": payload,
    }
    return payload


def _iter_json_state_rows(path: Path) -> Iterable[dict[str, Any]]:
    decoder = json.JSONDecoder()
    buffer = ""
    rows_started = False
    chunk_size = 1024 * 1024

    with path.open(encoding="utf-8") as handle:
        while True:
            if not rows_started:
                chunk = handle.read(chunk_size)
                if not chunk:
                    return
                buffer += chunk
                marker_index = buffer.find('"rows":[')
                if marker_index < 0:
                    buffer = buffer[-16:]
                    continue
                buffer = buffer[marker_index + len('"rows":['):]
                rows_started = True

            stripped = buffer.lstrip()
            if stripped.startswith("]"):
                return
            if stripped.startswith(","):
                buffer = stripped[1:]
                continue
            buffer = stripped

            try:
                row, end = decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                chunk = handle.read(chunk_size)
                if not chunk:
                    return
                buffer += chunk
                continue

            if isinstance(row, dict):
                yield row
            buffer = buffer[end:]


def _iter_feed_rows(config: ReviewOrdersFeedConfig) -> Iterable[dict[str, Any]]:
    if config.path and Path(config.path).suffix.casefold() == ".json":
        yield from _iter_json_state_rows(Path(config.path))
        return
    yield from load_review_orders_rows(config)


def get_xcelerator_gross_margin_snapshot(
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    config: ReviewOrdersFeedConfig | None = None,
    force_rebuild: bool = False,
) -> dict[str, Any]:
    """Return a fast gross-margin snapshot using Xcelerator-owned fields only."""

    window = _resolve_window(start=start, end=end)
    feed_config = config or _feed_config()
    required_config = [
        "FLEETPULSE_XCELERATOR_REVIEW_ORDERS_STATE_PATH",
    ]
    if not feed_config.configured:
        return {
            "status": "awaiting_feed",
            "source_authority": SOURCE_AUTHORITY,
            "projection_mode": PROJECTION_MODE,
            "period_start": window.start.isoformat(),
            "period_end": window.end.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "message": "Xcelerator gross margin feed is not configured.",
            "required_config": required_config,
            "summary": _finish_bucket(_empty_bucket("K1 total")),
            "entities": [],
            "weekly": [],
            "monthly": [],
            "monthly_entities": [],
            "row_count": 0,
            "excluded_row_count": 0,
            "source_method": "unconfigured",
        }

    signature = _source_signature(feed_config)
    cache_key = f"{window.start.isoformat()}:{window.end.isoformat()}:{signature[0]}"
    if not force_rebuild:
        if cached := _cached_snapshot(cache_key, signature):
            return cached
        if cached := _load_summary_cache(cache_key, signature, config=feed_config):
            return _store_cache(cache_key, signature, cached)
    if not force_rebuild and _should_skip_request_rebuild(feed_config, signature):
        return _missing_summary_cache_payload(window, required_config=required_config, signature=signature)

    try:
        rows = _iter_feed_rows(feed_config)
    except Exception as exc:
        return {
            "status": "unavailable",
            "source_authority": SOURCE_AUTHORITY,
            "projection_mode": PROJECTION_MODE,
            "period_start": window.start.isoformat(),
            "period_end": window.end.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "message": f"Xcelerator gross margin feed unavailable: {type(exc).__name__}",
            "required_config": required_config,
            "summary": _finish_bucket(_empty_bucket("K1 total")),
            "entities": [],
            "weekly": [],
            "monthly": [],
            "monthly_entities": [],
            "row_count": 0,
            "excluded_row_count": 0,
            "source_method": "unavailable",
        }

    entities = {
        K1L_ENTITY: _empty_bucket(K1L_ENTITY),
        K1G_ENTITY: _empty_bucket(K1G_ENTITY),
    }
    weekly: dict[str, dict[str, Any]] = {}
    monthly: dict[str, dict[str, Any]] = {}
    monthly_entities: dict[tuple[str, str], dict[str, Any]] = {}
    total = _empty_bucket("K1 total")
    source_methods: set[str] = set()
    excluded_row_count = 0
    included_row_count = 0
    row_dates: list[date] = []

    try:
        for row in rows:
            row_day = _row_day(row)
            if row_day is None or not (window.start <= row_day <= window.end):
                continue
            entity = _entity_from_delivery_center(_delivery_center(row))
            if entity is None:
                excluded_row_count += _order_count(row)
                continue

            orders = _order_count(row)
            revenue = _revenue(row)
            driver_pay = _driver_pay(row)
            gross_margin, source_method = _gross_margin(row)
            source_methods.add(source_method)
            row_dates.append(row_day)
            included_row_count += orders

            for bucket in (entities[entity], total):
                bucket["orders"] += orders
                bucket["revenue"] += revenue
                bucket["driver_pay"] += driver_pay
                bucket["gross_margin"] += gross_margin

            week = weekly.setdefault(
                _week_key(row_day),
                {
                    "week_start": _week_key(row_day),
                    "orders": 0,
                    "revenue": 0.0,
                    "driver_pay": 0.0,
                    "gross_margin": 0.0,
                    "gross_margin_pct": None,
                },
            )
            week["orders"] += orders
            week["revenue"] += revenue
            week["driver_pay"] += driver_pay
            week["gross_margin"] += gross_margin

            month = monthly.setdefault(
                _month_key(row_day),
                {
                    "entity": "K1 total",
                    "month_start": _month_key(row_day),
                    "orders": 0,
                    "revenue": 0.0,
                    "driver_pay": 0.0,
                    "gross_margin": 0.0,
                    "gross_margin_pct": None,
                },
            )
            month["orders"] += orders
            month["revenue"] += revenue
            month["driver_pay"] += driver_pay
            month["gross_margin"] += gross_margin

            entity_month_key = (entity, _month_key(row_day))
            entity_month = monthly_entities.setdefault(
                entity_month_key,
                {
                    "entity": entity,
                    "month_start": _month_key(row_day),
                    "orders": 0,
                    "revenue": 0.0,
                    "driver_pay": 0.0,
                    "gross_margin": 0.0,
                    "gross_margin_pct": None,
                },
            )
            entity_month["orders"] += orders
            entity_month["revenue"] += revenue
            entity_month["driver_pay"] += driver_pay
            entity_month["gross_margin"] += gross_margin
    except Exception as exc:
        return {
            "status": "unavailable",
            "source_authority": SOURCE_AUTHORITY,
            "projection_mode": PROJECTION_MODE,
            "period_start": window.start.isoformat(),
            "period_end": window.end.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "message": f"Xcelerator gross margin rows could not be summarized: {type(exc).__name__}",
            "required_config": required_config,
            "summary": _finish_bucket(_empty_bucket("K1 total")),
            "entities": [],
            "weekly": [],
            "monthly": [],
            "monthly_entities": [],
            "row_count": 0,
            "excluded_row_count": 0,
            "source_method": "unavailable",
        }

    finished_entities = [
        _finish_bucket(bucket)
        for bucket in entities.values()
        if int(bucket["orders"]) > 0 or float(bucket["revenue"]) != 0
    ]
    finished_weekly = [
        _finish_bucket({"entity": "K1 total", **row})
        for _, row in sorted(weekly.items())
    ]
    finished_monthly = [
        _finish_bucket(row)
        for _, row in sorted(monthly.items())
    ]
    finished_monthly_entities = [
        _finish_bucket(row)
        for _, row in sorted(monthly_entities.items(), key=lambda item: (item[0][1], item[0][0]))
    ]
    finished_summary = _finish_bucket(total)
    status = "healthy" if included_row_count and float(total["revenue"]) > 0 else "awaiting_feed"
    method = "+".join(sorted(source_methods)) or "no_matching_rows"
    if status == "healthy":
        coverage = ""
        if row_dates and (min(row_dates) > window.start or max(row_dates) < window.end):
            status = "partial"
            coverage = f" Rows cover {min(row_dates).isoformat()}..{max(row_dates).isoformat()}."
        message = (
            f"Read {included_row_count} K1 ReviewOrders row(s) for gross margin."
            f"{coverage}"
        )
    else:
        message = "Xcelerator ReviewOrders rows loaded, but no K1 gross-margin rows matched the requested window."

    payload = {
        "status": status,
        "source_authority": SOURCE_AUTHORITY,
        "projection_mode": PROJECTION_MODE,
        "period_start": window.start.isoformat(),
        "period_end": window.end.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "message": message,
        "required_config": required_config,
        "summary": finished_summary,
        "entities": finished_entities,
        "weekly": finished_weekly,
        "monthly": finished_monthly,
        "monthly_entities": finished_monthly_entities,
        "row_count": included_row_count,
        "excluded_row_count": excluded_row_count,
        "source_method": method,
        "last_updated": datetime.fromtimestamp(signature[1], tz=timezone.utc).isoformat()
        if signature[1]
        else None,
    }
    _save_summary_cache(cache_key, signature, payload, config=feed_config)
    return _store_cache(cache_key, signature, payload)


def get_gross_margin_rebuild_status() -> dict[str, Any]:
    with _REBUILD_LOCK:
        return dict(_REBUILD_STATUS)


def start_gross_margin_summary_rebuild(
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
) -> dict[str, Any]:
    with _REBUILD_LOCK:
        if _REBUILD_STATUS.get("status") == "running":
            return dict(_REBUILD_STATUS)
        _REBUILD_STATUS.update(
            {
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
                "message": "Xcelerator gross margin summary rebuild is running.",
                "snapshot": None,
            }
        )

    def rebuild() -> None:
        try:
            snapshot = get_xcelerator_gross_margin_snapshot(
                start=start,
                end=end,
                force_rebuild=True,
            )
            with _REBUILD_LOCK:
                _REBUILD_STATUS.update(
                    {
                        "status": "completed" if snapshot.get("status") in {"healthy", "partial"} else snapshot.get("status"),
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "message": snapshot.get("message"),
                        "snapshot": {
                            "status": snapshot.get("status"),
                            "period_start": snapshot.get("period_start"),
                            "period_end": snapshot.get("period_end"),
                            "row_count": snapshot.get("row_count"),
                            "source_method": snapshot.get("source_method"),
                            "summary": snapshot.get("summary"),
                            "monthly": snapshot.get("monthly"),
                            "monthly_entities": snapshot.get("monthly_entities"),
                        },
                    }
                )
        except Exception as exc:
            with _REBUILD_LOCK:
                _REBUILD_STATUS.update(
                    {
                        "status": "failed",
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "message": f"{type(exc).__name__}: {exc}",
                        "snapshot": None,
                    }
                )

    thread = threading.Thread(target=rebuild, name="gross-margin-summary-rebuild", daemon=True)
    thread.start()
    return get_gross_margin_rebuild_status()
