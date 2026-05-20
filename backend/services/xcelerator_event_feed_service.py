"""Scheduled Xcelerator event feed import for Control Tower.

Xcelerator remains authoritative for dispatch, load lifecycle, revenue, driver
pay, and exceptions. FleetPulse stores these rows as read-only event evidence so
Tower can work from a scheduled Zapier/Power Automate feed when a live URL is
not available.
"""

from __future__ import annotations

import csv
import io
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.idempotency import stable_idempotency_key


XCELERATOR_EVENT_AUTHORITY = "K1 Group LLC / Xcelerator event feed"
XCELERATOR_EVENT_NAMESPACE = "xcelerator_event_v1"
DEFAULT_XCELERATOR_EVENT_STATE_PATH = "/home/data/fleetpulse_xcelerator_events.json"
_STATE_LOCK = threading.RLock()


@dataclass(frozen=True)
class XceleratorEventFeedImportResult:
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
            "source_authority": XCELERATOR_EVENT_AUTHORITY,
            "projection_mode": "read_only",
            "dry_run": self.dry_run,
            "total_records": self.total_records,
            "imported_count": self.imported_count,
            "duplicate_count": self.duplicate_count,
            "invalid_count": self.invalid_count,
            "errors": self.errors,
            "summary": self.summary,
        }


class XceleratorEventStateStore:
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
            raise RuntimeError("xcelerator_event_state_invalid")
        payload.setdefault("processed_idempotency_keys", [])
        payload.setdefault("rows", [])
        payload.setdefault("last_imported_at", None)
        return payload

    def save_state(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp_path.write_text(
            json.dumps(state, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        tmp_path.replace(self.path)

    def rows(self) -> list[dict[str, Any]]:
        with _STATE_LOCK:
            state = self.load_state()
        rows = [row for row in state.get("rows", []) if isinstance(row, dict)]
        rows.sort(key=lambda item: str(_row_timestamp(item) or ""), reverse=True)
        return rows

    def state_metadata(self) -> dict[str, Any]:
        with _STATE_LOCK:
            state = self.load_state()
        timestamps = [_row_timestamp(row) for row in state.get("rows", []) if isinstance(row, dict)]
        timestamps = [value for value in timestamps if value]
        return {
            "last_imported_at": state.get("last_imported_at"),
            "last_updated": max(timestamps).isoformat() if timestamps else state.get("last_imported_at"),
        }

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
                existing_rows.sort(key=lambda item: str(_row_timestamp(item) or ""), reverse=True)
                state["rows"] = existing_rows[: self.retained_record_limit]
                state["processed_idempotency_keys"] = processed_keys[-self.retained_record_limit * 2 :]
                state["last_imported_at"] = datetime.now(timezone.utc).isoformat()
                self.save_state(state)

            return imported, duplicates, accepted


def import_xcelerator_events(
    content: str,
    *,
    filename: str | None = None,
    dry_run: bool = False,
    store: XceleratorEventStateStore | None = None,
) -> XceleratorEventFeedImportResult:
    store = store or XceleratorEventStateStore()
    rows, errors = parse_xcelerator_event_content(content, filename=filename)
    imported, duplicates, accepted = store.append_rows(rows, dry_run=dry_run)
    invalid_count = len(errors)
    status = "ok" if imported or duplicates or not invalid_count else "invalid"
    return XceleratorEventFeedImportResult(
        status=status,
        dry_run=dry_run,
        total_records=len(rows) + invalid_count,
        imported_count=imported,
        duplicate_count=duplicates,
        invalid_count=invalid_count,
        errors=errors,
        summary=summarize_xcelerator_events(accepted),
    )


def parse_xcelerator_event_content(
    content: str,
    *,
    filename: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows = _load_export_rows(content, filename=filename)
    accepted: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        normalized = {str(key).strip(): value for key, value in row.items() if str(key).strip()}
        if not any(str(value or "").strip() for value in normalized.values()):
            continue
        if not _first_value(
            normalized,
            "event_type",
            "eventType",
            "workflow_name",
            "workflowName",
            "status",
            "exception_status",
            "exceptionStatus",
        ):
            errors.append(f"row {index}: missing Xcelerator event type/status")
            continue
        accepted.append(normalized)
    return accepted, errors


def load_xcelerator_event_state_rows(
    *,
    store: XceleratorEventStateStore | None = None,
) -> tuple[list[dict[str, Any]], datetime | None]:
    store = store or XceleratorEventStateStore()
    rows = store.rows()
    metadata = store.state_metadata()
    last_updated = _parse_datetime(metadata.get("last_updated"))
    return rows, last_updated


def xcelerator_event_feed_status(
    *,
    store: XceleratorEventStateStore | None = None,
) -> dict[str, Any]:
    store = store or XceleratorEventStateStore()
    rows = store.rows() if store.path.exists() else []
    metadata = store.state_metadata() if store.path.exists() else {}
    configured = bool(_configured_state_path_text())
    return {
        "source_authority": XCELERATOR_EVENT_AUTHORITY,
        "projection_mode": "read_only",
        "status": "healthy" if rows else "awaiting_feed",
        "state_path": str(store.path),
        "state_path_configured": configured,
        "missing_config": [] if configured else ["FLEETPULSE_XCELERATOR_EVENT_STATE_PATH"],
        "row_count": len(rows),
        "last_imported_at": metadata.get("last_imported_at"),
        "last_updated": metadata.get("last_updated"),
        "summary": summarize_xcelerator_events(rows),
    }


def summarize_xcelerator_events(rows: list[dict[str, Any]]) -> dict[str, Any]:
    financial_count = 0
    attention_count = 0
    latest: datetime | None = None
    for row in rows:
        if _first_value(
            row,
            "revenue_amount",
            "revenueAmount",
            "driver_pay_amount",
            "driverPayAmount",
            "gross_margin",
            "grossMargin",
        ) is not None:
            financial_count += 1
        event_type = str(_first_value(row, "event_type", "eventType", "workflow_name", "workflowName") or "").lower()
        status = str(_first_value(row, "status", "exception_status", "exceptionStatus") or "").lower()
        if "exception" in event_type or status in {"exception", "failed", "failure", "late", "missed", "overdue", "open"}:
            attention_count += 1
        timestamp = _row_timestamp(row)
        if timestamp and (latest is None or timestamp > latest):
            latest = timestamp
    return {
        "row_count": len(rows),
        "financial_row_count": financial_count,
        "attention_row_count": attention_count,
        "last_updated": latest.isoformat() if latest else None,
    }


def validate_xcelerator_event_import_api_key(provided: str | None) -> None:
    expected = (
        os.getenv("FLEETPULSE_XCELERATOR_EVENT_IMPORT_API_KEY", "").strip()
        or os.getenv("FLEETPULSE_XCELERATOR_EVENT_FEED_API_KEY", "").strip()
    )
    if expected and provided != expected:
        raise PermissionError("Invalid Xcelerator event import API key")


def xcelerator_event_state_configured() -> bool:
    return bool(_configured_state_path_text())


def _load_export_rows(content: str, *, filename: str | None = None) -> list[dict[str, Any]]:
    stripped = content.lstrip("\ufeff").strip()
    if not stripped:
        return []
    suffix = Path(str(filename or "")).suffix.casefold()
    if suffix == ".json" or stripped[:1] in {"[", "{"}:
        return _rows_from_json(json.loads(stripped))
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


def _rows_from_json(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("events", "items", "rows", "data", "value", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    tables = payload.get("tables")
    if isinstance(tables, dict):
        for value in tables.values():
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _row_idempotency_key(row: dict[str, Any]) -> str:
    existing = _first_value(row, "_fleetpulse_idempotency_key", "idempotency_key", "event_id", "eventId", "id")
    if existing:
        return str(existing)
    return stable_idempotency_key(
        XCELERATOR_EVENT_NAMESPACE,
        _first_value(row, "event_type", "eventType", "workflow_name", "workflowName"),
        _first_value(row, "route_id", "routeId", "shipment_id", "shipmentId", "order_id", "orderId"),
        _first_value(row, "status", "exception_status", "exceptionStatus"),
        _first_value(row, "timestamp", "updated_at", "updatedAt", "created_at", "createdAt"),
    )


def _row_timestamp(row: dict[str, Any]) -> datetime | None:
    return _parse_datetime(
        _first_value(
            row,
            "timestamp",
            "updated_at",
            "updatedAt",
            "created_at",
            "createdAt",
            "detected_at",
            "detectedAt",
        )
    )


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _first_value(record: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = record.get(name)
        if value not in (None, ""):
            return value
    return None


def _configured_state_path_text() -> str:
    return os.getenv("FLEETPULSE_XCELERATOR_EVENT_STATE_PATH", "").strip()


def _state_path_from_env() -> Path:
    return Path(_configured_state_path_text() or DEFAULT_XCELERATOR_EVENT_STATE_PATH)


def _retained_record_limit_from_env() -> int:
    try:
        return max(int(os.getenv("FLEETPULSE_XCELERATOR_EVENT_RETAINED_RECORDS", "50000")), 1)
    except ValueError:
        return 50000
