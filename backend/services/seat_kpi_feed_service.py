"""Read-only scheduled feed state for missing Control Tower seat KPIs.

Xcelerator, QuickBooks, and SharePoint remain authoritative. FleetPulse stores
scheduled exports only as KPI evidence so Control Tower can show source
readiness without creating or overwriting operational records.
"""

from __future__ import annotations

import csv
import io
import json
import os
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

from utils.idempotency import stable_idempotency_key


DEFAULT_ROOT = "/home/data"
_STATE_LOCK = threading.RLock()


@dataclass(frozen=True)
class SeatKpiFeedSpec:
    key: str
    label: str
    source_authority: str
    state_path_env: str
    import_key_env: str
    default_filename: str
    required_groups: tuple[tuple[str, ...], ...]
    identifier_fields: tuple[str, ...]
    timestamp_fields: tuple[str, ...]
    status_fields: tuple[str, ...] = ("status", "Status")

    @property
    def default_state_path(self) -> str:
        return str(Path(os.getenv("FLEETPULSE_SEAT_KPI_STATE_PATH_ROOT", DEFAULT_ROOT)) / self.default_filename)


FEED_SPECS: dict[str, SeatKpiFeedSpec] = {
    "billing_exceptions": SeatKpiFeedSpec(
        key="billing_exceptions",
        label="Billing Exception Aging",
        source_authority="K1 Group LLC / Xcelerator + SharePoint billing packets",
        state_path_env="FLEETPULSE_BILLING_EXCEPTIONS_STATE_PATH",
        import_key_env="FLEETPULSE_BILLING_EXCEPTIONS_IMPORT_API_KEY",
        default_filename="fleetpulse_billing_exceptions.json",
        required_groups=(
            ("exception_id", "Exception ID", "billing_exception_id", "order_id", "Order ID", "shipment_id"),
            ("status", "Status", "exception_status", "Exception Status"),
            ("created_at", "Created At", "opened_at", "Opened At", "age_start_at"),
        ),
        identifier_fields=("exception_id", "billing_exception_id", "order_id", "shipment_id"),
        timestamp_fields=("updated_at", "Updated At", "created_at", "Created At", "opened_at", "Opened At"),
    ),
    "weekly_close_variance": SeatKpiFeedSpec(
        key="weekly_close_variance",
        label="Weekly Close Variance",
        source_authority="K1 Group LLC / QuickBooks + SharePoint close ledger",
        state_path_env="FLEETPULSE_WEEKLY_CLOSE_VARIANCE_STATE_PATH",
        import_key_env="FLEETPULSE_WEEKLY_CLOSE_VARIANCE_IMPORT_API_KEY",
        default_filename="fleetpulse_weekly_close_variance.json",
        required_groups=(
            ("week_start", "Week Start", "week_ending", "Week Ending"),
            ("variance_amount", "Variance Amount", "variance", "Variance"),
            ("status", "Status", "close_status", "Close Status"),
        ),
        identifier_fields=("week_start", "week_ending", "ledger_id", "close_id"),
        timestamp_fields=("updated_at", "Updated At", "closed_at", "Closed At", "week_start", "Week Start"),
        status_fields=("status", "Status", "close_status", "Close Status"),
    ),
    "dispatch_timestamps": SeatKpiFeedSpec(
        key="dispatch_timestamps",
        label="Dispatch Timestamp Feed",
        source_authority="K1 Group LLC / Xcelerator dispatch lifecycle",
        state_path_env="FLEETPULSE_DISPATCH_TIMESTAMPS_STATE_PATH",
        import_key_env="FLEETPULSE_DISPATCH_TIMESTAMPS_IMPORT_API_KEY",
        default_filename="fleetpulse_dispatch_timestamps.json",
        required_groups=(
            ("load_id", "Load ID", "order_id", "Order ID", "shipment_id", "route_id"),
            ("ready_at", "Ready At", "assigned_at", "Assigned At", "accepted_at", "Accepted At", "dispatched_at", "Dispatched At"),
        ),
        identifier_fields=("load_id", "order_id", "shipment_id", "route_id"),
        timestamp_fields=("updated_at", "Updated At", "dispatched_at", "Dispatched At", "assigned_at", "Assigned At", "ready_at", "Ready At"),
    ),
    "sharepoint_seat_assignments": SeatKpiFeedSpec(
        key="sharepoint_seat_assignments",
        label="SharePoint Seat Assignments",
        source_authority="K1 Workforce Intelligence / SharePoint Seat_Assignments",
        state_path_env="FLEETPULSE_SHAREPOINT_SEAT_ASSIGNMENTS_STATE_PATH",
        import_key_env="FLEETPULSE_SHAREPOINT_SEAT_ASSIGNMENTS_IMPORT_API_KEY",
        default_filename="fleetpulse_sharepoint_seat_assignments.json",
        required_groups=(
            ("seat_id", "Seat ID", "seat", "Seat"),
            ("employee_id", "Employee ID", "user_principal_name", "UPN", "email"),
            ("status", "Status", "assignment_status", "Assignment Status"),
        ),
        identifier_fields=("seat_id", "employee_id", "user_principal_name", "email"),
        timestamp_fields=("updated_at", "Updated At", "assigned_at", "Assigned At", "effective_at", "Effective At"),
        status_fields=("status", "Status", "assignment_status", "Assignment Status"),
    ),
    "sharepoint_training_history": SeatKpiFeedSpec(
        key="sharepoint_training_history",
        label="SharePoint Training History",
        source_authority="K1 Workforce Intelligence / SharePoint Training_History",
        state_path_env="FLEETPULSE_SHAREPOINT_TRAINING_HISTORY_STATE_PATH",
        import_key_env="FLEETPULSE_SHAREPOINT_TRAINING_HISTORY_IMPORT_API_KEY",
        default_filename="fleetpulse_sharepoint_training_history.json",
        required_groups=(
            ("employee_id", "Employee ID", "user_principal_name", "UPN", "email"),
            ("training_id", "Training ID", "course", "Course", "module", "Module"),
            ("status", "Status", "completed_at", "Completed At", "completion_date", "Completion Date"),
        ),
        identifier_fields=("employee_id", "user_principal_name", "email", "training_id", "course"),
        timestamp_fields=("updated_at", "Updated At", "completed_at", "Completed At", "completion_date", "Completion Date", "due_date", "Due Date"),
    ),
}


@dataclass(frozen=True)
class SeatKpiFeedImportResult:
    status: str
    feed_key: str
    dry_run: bool
    total_records: int
    imported_count: int
    duplicate_count: int
    invalid_count: int
    errors: list[str]
    state_path: str
    summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        spec = _spec(self.feed_key)
        return {
            "status": self.status,
            "feed_key": self.feed_key,
            "feed_label": spec.label,
            "source_authority": spec.source_authority,
            "projection_mode": "read_only",
            "dry_run": self.dry_run,
            "total_records": self.total_records,
            "imported_count": self.imported_count,
            "duplicate_count": self.duplicate_count,
            "invalid_count": self.invalid_count,
            "errors": self.errors,
            "state_path": self.state_path,
            "summary": self.summary,
        }


class SeatKpiFeedStateStore:
    def __init__(self, spec: SeatKpiFeedSpec, path: Path | str | None = None):
        self.spec = spec
        self.path = Path(path) if path else _state_path_from_env(spec)
        self.retained_record_limit = _retained_record_limit_from_env()

    def _empty_state(self) -> dict[str, Any]:
        return {
            "version": 1,
            "feed_key": self.spec.key,
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
            raise RuntimeError("seat_kpi_feed_state_invalid")
        payload.setdefault("feed_key", self.spec.key)
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
        rows.sort(key=lambda item: str(_row_timestamp(self.spec, item) or ""), reverse=True)
        return rows

    def metadata(self) -> dict[str, Any]:
        with _STATE_LOCK:
            state = self.load_state()
        timestamps = [_row_timestamp(self.spec, row) for row in state.get("rows", []) if isinstance(row, dict)]
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
                key = _row_idempotency_key(self.spec, row)
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
                existing_rows.sort(key=lambda item: str(_row_timestamp(self.spec, item) or ""), reverse=True)
                state["rows"] = existing_rows[: self.retained_record_limit]
                state["processed_idempotency_keys"] = processed_keys[-self.retained_record_limit * 2 :]
                state["last_imported_at"] = datetime.now(timezone.utc).isoformat()
                self.save_state(state)

            return imported, duplicates, accepted


def list_seat_kpi_feed_statuses() -> dict[str, Any]:
    statuses = [get_seat_kpi_feed_status(key) for key in FEED_SPECS]
    healthy = sum(1 for item in statuses if item["status"] == "healthy")
    awaiting = sum(1 for item in statuses if item["status"] == "awaiting_feed")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "projection_mode": "read_only",
        "source_authority": "FleetPulse scheduled seat KPI feed registry",
        "summary": {
            "total": len(statuses),
            "healthy": healthy,
            "awaiting_feed": awaiting,
            "coverage_pct": round((healthy / len(statuses)) * 100, 1) if statuses else 0.0,
        },
        "feeds": statuses,
    }


def get_seat_kpi_feed_status(feed_key: str, *, store: SeatKpiFeedStateStore | None = None) -> dict[str, Any]:
    spec = _spec(feed_key)
    store = store or SeatKpiFeedStateStore(spec)
    configured = bool(os.getenv(spec.state_path_env, "").strip())
    exists = store.path.exists()
    rows = store.rows() if exists else []
    metadata = store.metadata() if exists else {}
    return {
        "feed_key": spec.key,
        "feed_label": spec.label,
        "source_authority": spec.source_authority,
        "projection_mode": "read_only",
        "status": "healthy" if rows else "awaiting_feed",
        "state_path": str(store.path),
        "state_path_configured": configured,
        "missing_config": [] if configured else [spec.state_path_env],
        "import_key_configured": bool(
            os.getenv(spec.import_key_env, "").strip() or os.getenv("FLEETPULSE_SEAT_KPI_IMPORT_API_KEY", "").strip()
        ),
        "row_count": len(rows),
        "last_imported_at": metadata.get("last_imported_at"),
        "last_updated": metadata.get("last_updated"),
        "summary": summarize_seat_kpi_feed(spec.key, rows),
    }


def import_seat_kpi_feed(
    feed_key: str,
    content: str,
    *,
    filename: str | None = None,
    dry_run: bool = False,
    store: SeatKpiFeedStateStore | None = None,
) -> SeatKpiFeedImportResult:
    spec = _spec(feed_key)
    store = store or SeatKpiFeedStateStore(spec)
    rows, errors = parse_seat_kpi_feed_content(spec.key, content, filename=filename)
    imported, duplicates, accepted = store.append_rows(rows, dry_run=dry_run)
    invalid_count = len(errors)
    status = "ok" if imported or duplicates or not invalid_count else "invalid"
    return SeatKpiFeedImportResult(
        status=status,
        feed_key=spec.key,
        dry_run=dry_run,
        total_records=len(rows) + invalid_count,
        imported_count=imported,
        duplicate_count=duplicates,
        invalid_count=invalid_count,
        errors=errors,
        state_path=str(store.path),
        summary=summarize_seat_kpi_feed(spec.key, accepted),
    )


def parse_seat_kpi_feed_content(
    feed_key: str,
    content: str,
    *,
    filename: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    spec = _spec(feed_key)
    rows = _load_export_rows(content, filename=filename)
    accepted: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        normalized = {str(key).strip(): value for key, value in row.items() if str(key).strip()}
        if not any(str(value or "").strip() for value in normalized.values()):
            continue
        missing = _missing_required_groups(spec, normalized)
        if missing:
            errors.append(f"row {index}: missing {', '.join(missing)}")
            continue
        accepted.append(normalized)
    return accepted, errors


def summarize_seat_kpi_feed(feed_key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    spec = _spec(feed_key)
    timestamps = [_row_timestamp(spec, row) for row in rows]
    timestamps = [value for value in timestamps if value]
    latest = max(timestamps) if timestamps else None
    summary: dict[str, Any] = {
        "row_count": len(rows),
        "last_updated": latest.isoformat() if latest else None,
    }
    status_counts = Counter(_status_key(_first_value(row, *spec.status_fields)) or "unknown" for row in rows)
    summary["status_counts"] = dict(sorted(status_counts.items()))

    if spec.key == "billing_exceptions":
        open_rows = [row for row in rows if not _is_closed(_first_value(row, *spec.status_fields))]
        now = datetime.now(timezone.utc)
        over_48h = 0
        for row in open_rows:
            opened = _row_timestamp(spec, row)
            if opened and (now - opened).total_seconds() >= 48 * 3600:
                over_48h += 1
        summary.update({"open_count": len(open_rows), "over_48h_count": over_48h})
    elif spec.key == "weekly_close_variance":
        variances = [_number(_first_value(row, "variance_amount", "Variance Amount", "variance", "Variance")) for row in rows]
        open_rows = [row for row in rows if not _is_closed(_first_value(row, *spec.status_fields))]
        summary.update(
            {
                "open_count": len(open_rows),
                "total_abs_variance": round(sum(abs(value) for value in variances), 2),
                "latest_week": _latest_date_text(rows, ("week_start", "Week Start", "week_ending", "Week Ending")),
            }
        )
    elif spec.key == "dispatch_timestamps":
        late_count = sum(1 for row in rows if _truthy(_first_value(row, "late", "Late", "is_late", "late_dispatch", "Late Dispatch")))
        missing_dispatch = sum(1 for row in rows if not _first_value(row, "dispatched_at", "Dispatched At", "accepted_at", "Accepted At"))
        summary.update({"late_dispatch_count": late_count, "missing_dispatch_timestamp_count": missing_dispatch})
    elif spec.key == "sharepoint_seat_assignments":
        active_rows = [row for row in rows if not _is_closed(_first_value(row, *spec.status_fields))]
        seats = {_text(_first_value(row, "seat_id", "Seat ID", "seat", "Seat")) for row in active_rows}
        seats.discard("")
        summary.update({"active_assignment_count": len(active_rows), "filled_seat_count": len(seats)})
    elif spec.key == "sharepoint_training_history":
        completed = sum(1 for row in rows if _is_closed(_first_value(row, *spec.status_fields)) or _first_value(row, "completed_at", "Completed At", "completion_date", "Completion Date"))
        summary.update({"completed_count": completed, "incomplete_count": max(len(rows) - completed, 0)})

    return summary


def validate_seat_kpi_feed_import_api_key(feed_key: str, provided: str | None) -> None:
    spec = _spec(feed_key)
    expected = (
        os.getenv(spec.import_key_env, "").strip()
        or os.getenv("FLEETPULSE_SEAT_KPI_IMPORT_API_KEY", "").strip()
    )
    if expected and provided != expected:
        raise PermissionError(f"Invalid {spec.key} import API key")


def feed_state_path_env(feed_key: str) -> str:
    return _spec(feed_key).state_path_env


def _spec(feed_key: str) -> SeatKpiFeedSpec:
    key = str(feed_key or "").strip()
    if key not in FEED_SPECS:
        raise KeyError(f"Unknown seat KPI feed: {feed_key}")
    return FEED_SPECS[key]


def _state_path_from_env(spec: SeatKpiFeedSpec) -> Path:
    return Path(os.getenv(spec.state_path_env, "").strip() or spec.default_state_path)


def _retained_record_limit_from_env() -> int:
    try:
        return max(int(os.getenv("FLEETPULSE_SEAT_KPI_RETAINED_RECORDS", "5000")), 1)
    except ValueError:
        return 5000


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
    for key in ("rows", "items", "records", "data", "value", "events"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _missing_required_groups(spec: SeatKpiFeedSpec, row: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for group in spec.required_groups:
        if _first_value(row, *group) in (None, ""):
            missing.append(group[0])
    return missing


def _row_idempotency_key(spec: SeatKpiFeedSpec, row: dict[str, Any]) -> str:
    existing = _first_value(row, "_fleetpulse_idempotency_key", "idempotency_key", "event_id", "id")
    if existing:
        return str(existing)
    return stable_idempotency_key(
        f"seat_kpi_{spec.key}_v1",
        *[_first_value(row, field) for field in spec.identifier_fields],
        *[_first_value(row, field) for field in spec.timestamp_fields],
        _first_value(row, *spec.status_fields),
    )


def _row_timestamp(spec: SeatKpiFeedSpec, row: dict[str, Any]) -> datetime | None:
    for field in spec.timestamp_fields:
        parsed = _parse_datetime(_first_value(row, field))
        if parsed:
            return parsed
    for field in ("timestamp", "Timestamp", "created_at", "Created At", "updated_at", "Updated At"):
        parsed = _parse_datetime(_first_value(row, field))
        if parsed:
            return parsed
    return None


def _first_value(row: dict[str, Any], *keys: str) -> Any:
    normalized = {_normalize_key(key): value for key, value in row.items()}
    for key in keys:
        value = normalized.get(_normalize_key(key))
        if value not in (None, ""):
            return value
    return None


def _normalize_key(value: str) -> str:
    return "".join(ch for ch in str(value).casefold() if ch.isalnum())


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _status_key(value: Any) -> str:
    return _normalize_key(_text(value)) or "unknown"


def _is_closed(value: Any) -> bool:
    return _status_key(value) in {
        "closed",
        "complete",
        "completed",
        "done",
        "finished",
        "resolved",
        "reconciled",
        "filled",
        "activefilled",
        "trained",
        "passed",
    }


def _truthy(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y", "late", "overdue"}


def _number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except ValueError:
        return 0.0


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    raw = str(value).strip()
    if not raw:
        return None
    if raw.isdigit():
        try:
            numeric = float(raw)
            if numeric > 10_000_000_000:
                numeric /= 1000
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    normalized = raw.replace("Z", "+00:00")
    try:
        return _ensure_aware(datetime.fromisoformat(normalized))
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%m/%d/%Y %H:%M", "%m/%d/%Y %I:%M %p", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _latest_date_text(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> str | None:
    values = [_parse_datetime(_first_value(row, *fields)) for row in rows]
    values = [value for value in values if value]
    return max(values).date().isoformat() if values else None
