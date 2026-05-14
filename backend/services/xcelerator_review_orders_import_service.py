"""Manual Xcelerator ReviewOrders import service.

This stores downloaded ReviewOrders rows as read-only evidence for FleetPulse
analytics. Xcelerator remains the source of truth for orders, revenue, and
driver pay; this service only preserves exported rows for reporting.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import csv
import io
import json
import os
from pathlib import Path
import re
import threading
from typing import Any

from utils.idempotency import stable_idempotency_key


XCELERATOR_REVIEW_ORDERS_AUTHORITY = "K1 Group LLC / Xcelerator ReviewOrders export"
XCELERATOR_REVIEW_ORDERS_NAMESPACE = "xcelerator_review_orders_v1"
_STATE_LOCK = threading.Lock()


@dataclass(frozen=True)
class XceleratorReviewOrdersImportResult:
    status: str
    dry_run: bool
    total_records: int
    imported_count: int
    duplicate_count: int
    invalid_count: int
    errors: list[str]
    summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_authority": XCELERATOR_REVIEW_ORDERS_AUTHORITY,
            "projection_mode": "read_only",
            "dry_run": self.dry_run,
            "total_records": self.total_records,
            "imported_count": self.imported_count,
            "duplicate_count": self.duplicate_count,
            "invalid_count": self.invalid_count,
            "errors": self.errors,
            "summary": self.summary,
        }


class XceleratorReviewOrdersStateStore:
    def __init__(self, path: Path | str | None = None, retained_record_limit: int | None = None):
        self.path = Path(path) if path else _state_path_from_env()
        self.retained_record_limit = retained_record_limit or _retained_record_limit_from_env()

    def _empty_state(self) -> dict[str, Any]:
        return {
            "version": 1,
            "processed_idempotency_keys": [],
            "rows": [],
            "last_imported_at": None,
        }

    def load_state(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty_state()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return {
                **self._empty_state(),
                "rows": [row for row in payload if isinstance(row, dict)],
            }
        if not isinstance(payload, dict):
            raise RuntimeError("xcelerator_review_orders_state_invalid")
        payload.setdefault("processed_idempotency_keys", [])
        payload.setdefault("rows", [])
        payload.setdefault("last_imported_at", None)
        return payload

    def save_state(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp_path.write_text(json.dumps(state, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        tmp_path.replace(self.path)

    def rows(self) -> list[dict[str, Any]]:
        with _STATE_LOCK:
            state = self.load_state()
        rows = [row for row in state.get("rows", []) if isinstance(row, dict)]
        rows.sort(key=lambda item: str(_row_date(item) or ""), reverse=True)
        return rows

    def append_rows(self, rows: list[dict[str, Any]], *, dry_run: bool = False) -> tuple[int, int, list[dict[str, Any]]]:
        with _STATE_LOCK:
            state = self.load_state()
            processed_keys = [str(key) for key in state.get("processed_idempotency_keys", [])]
            processed = set(processed_keys)
            existing_rows = [row for row in state.get("rows", []) if isinstance(row, dict)]
            imported = 0
            duplicates = 0
            accepted: list[dict[str, Any]] = []

            for row in rows:
                key = _row_idempotency_key(row)
                if key in processed:
                    duplicates += 1
                    continue
                accepted_row = {**row, "_fleetpulse_idempotency_key": key}
                accepted.append(accepted_row)
                imported += 1
                if not dry_run:
                    processed.add(key)
                    processed_keys.append(key)
                    existing_rows.append(accepted_row)

            if not dry_run:
                existing_rows.sort(key=lambda item: str(_row_date(item) or ""), reverse=True)
                state["rows"] = existing_rows[: self.retained_record_limit]
                state["processed_idempotency_keys"] = processed_keys[-self.retained_record_limit * 2 :]
                state["last_imported_at"] = datetime.now(timezone.utc).isoformat()
                self.save_state(state)

            return imported, duplicates, accepted


def import_xcelerator_review_orders(
    content: str,
    *,
    filename: str | None = None,
    dry_run: bool = False,
    store: XceleratorReviewOrdersStateStore | None = None,
) -> XceleratorReviewOrdersImportResult:
    store = store or XceleratorReviewOrdersStateStore()
    rows, errors = parse_review_orders_export_content(content, filename=filename)
    imported, duplicates, accepted = store.append_rows(rows, dry_run=dry_run)
    invalid_count = len(errors)
    status = "ok" if imported or duplicates or not invalid_count else "invalid"
    return XceleratorReviewOrdersImportResult(
        status=status,
        dry_run=dry_run,
        total_records=len(rows) + invalid_count,
        imported_count=imported,
        duplicate_count=duplicates,
        invalid_count=invalid_count,
        errors=errors,
        summary=summarize_review_orders(accepted),
    )


def parse_review_orders_export_content(content: str, *, filename: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    rows = _load_export_rows(content, filename)
    accepted: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        normalized = {str(key).strip(): value for key, value in row.items() if str(key).strip()}
        if not any(str(value or "").strip() for value in normalized.values()):
            continue
        if not _row_date(normalized):
            if _row_has_money(normalized):
                errors.append(f"row {index}: missing ReviewOrders date")
            continue
        if not any((_driver_pay(normalized), _revenue(normalized), _order_id(normalized))):
            continue
        accepted.append(normalized)
    return accepted, errors


def summarize_review_orders(rows: list[dict[str, Any]], *, days: int | None = None) -> dict[str, Any]:
    if days is not None:
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=max(min(days, 370), 1))
        rows = [row for row in rows if (row_day := _row_date(row)) and row_day >= cutoff]
    dated = [(row, row_day) for row in rows if (row_day := _row_date(row))]
    driver_pay = sum(_driver_pay(row) for row, _ in dated)
    revenue = sum(_revenue(row) for row, _ in dated)
    order_ids = {_order_id(row) for row, _ in dated if _order_id(row)}
    return {
        "row_count": len(rows),
        "dated_row_count": len(dated),
        "order_count": len(order_ids) or len(dated),
        "date_min": min((row_day for _, row_day in dated), default=None).isoformat() if dated else None,
        "date_max": max((row_day for _, row_day in dated), default=None).isoformat() if dated else None,
        "driver_pay_total": round(driver_pay, 2),
        "revenue_total": round(revenue, 2),
    }


def get_xcelerator_review_orders_summary(
    days: int = 370,
    *,
    store: XceleratorReviewOrdersStateStore | None = None,
) -> dict[str, Any]:
    rows = (store or XceleratorReviewOrdersStateStore()).rows()
    return {
        "source_authority": XCELERATOR_REVIEW_ORDERS_AUTHORITY,
        "projection_mode": "read_only",
        "period_days": days,
        **summarize_review_orders(rows, days=days),
    }


def _state_path_from_env() -> Path:
    configured = (
        os.getenv("FLEETPULSE_XCELERATOR_REVIEW_ORDERS_STATE_PATH", "").strip()
        or os.getenv("FLEETPULSE_LANE_STABILITY_ORDER_FEED_PATH", "").strip()
    )
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "data" / "xcelerator_review_orders.json"


def _retained_record_limit_from_env() -> int:
    try:
        return max(int(os.getenv("FLEETPULSE_XCELERATOR_REVIEW_ORDERS_RETAINED_RECORDS", "50000")), 1)
    except ValueError:
        return 50000


def _load_export_rows(content: str, filename: str | None) -> list[dict[str, Any]]:
    text = (content or "").lstrip("\ufeff").strip()
    if not text:
        return []
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".json", ".jsonl"} or text[:1] in {"[", "{"}:
        payload = json.loads(text)
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            for key in ("rows", "orders", "data", "items", "value"):
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
    normalized = {_normalize(alias) for alias in aliases}
    for key, value in row.items():
        if _normalize(key) in normalized:
            return value
    return None


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("$", "").replace(",", "")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else 0.0


def _coerce_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and value > 20000:
        return date(1899, 12, 30) + timedelta(days=int(value))
    text = str(value or "").strip()
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


def _row_date(row: dict[str, Any]) -> date | None:
    return _coerce_date(
        _find_value(
            row,
            (
                "[P]From Date",
                "PFrom Date",
                "From Date",
                "Order Date",
                "date",
            ),
        )
    )


def _order_id(row: dict[str, Any]) -> str:
    value = _find_value(row, ("OrderTrackingID", "Order ID", "OrderId", "Load ID", "Shipment ID"))
    return str(value or "").strip()


def _driver_pay(row: dict[str, Any]) -> float:
    return _number(_find_value(row, ("Driver Pay", "driver_pay", "DriverPay")))


def _revenue(row: dict[str, Any]) -> float:
    return _number(_find_value(row, ("Grand Total", "grand_total", "GrandTotal", "Revenue")))


def _order_charge(row: dict[str, Any]) -> float:
    return _number(_find_value(row, ("Order Charge", "order_charge", "OrderCharge")))


def _driver(row: dict[str, Any]) -> str:
    return str(_find_value(row, ("DriverNo", "Driver No", "Driver")) or "").strip()


def _route(row: dict[str, Any]) -> str:
    return str(_find_value(row, ("RouteNo", "Route No", "Route")) or "").strip()


def _row_has_money(row: dict[str, Any]) -> bool:
    return any((_driver_pay(row), _revenue(row), _order_charge(row)))


def _row_idempotency_key(row: dict[str, Any]) -> str:
    return stable_idempotency_key(
        XCELERATOR_REVIEW_ORDERS_NAMESPACE,
        _order_id(row),
        _row_date(row).isoformat() if _row_date(row) else "",
        _driver(row),
        _route(row),
        round(_driver_pay(row), 2),
        round(_revenue(row), 2),
    )
