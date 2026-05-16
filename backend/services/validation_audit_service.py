"""Durable validation probe audit records for dashboard badges.

The audit log is a read-only proof ledger for FleetPulse validation checks. It
records probe outcomes; it does not write back to Geotab, Xcelerator, QBO, or
any other source-of-truth system.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


_LOCK = threading.Lock()


def _state_path() -> Path:
    configured = os.getenv("FLEETPULSE_VALIDATION_AUDIT_PATH", "").strip()
    return Path(configured or "/home/data/fleetpulse_validation_audit.json")


def _retained_records() -> int:
    try:
        return max(int(os.getenv("FLEETPULSE_VALIDATION_AUDIT_RETAINED_RECORDS", "5000")), 100)
    except ValueError:
        return 5000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {"records": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"records": []}
    if not isinstance(data, dict):
        return {"records": []}
    records = data.get("records")
    if not isinstance(records, list):
        data["records"] = []
    return data


def _write_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f"{path.suffix}.tmp")
    temp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def record_probe(
    probe_name: str,
    status: str,
    *,
    reason: str,
    rowcount: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "metadata": metadata or {},
        "probe_name": probe_name,
        "reason": reason,
        "rowcount": rowcount,
        "status": status,
        "timestamp": _now().isoformat(),
    }
    with _LOCK:
        state = _load_state()
        records = [item for item in state.get("records", []) if isinstance(item, dict)]
        records.append(record)
        state["records"] = records[-_retained_records():]
        _write_state(state)
    return record


def recent_records(probe_name: str, *, within_minutes: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
    cutoff = _now() - timedelta(minutes=within_minutes) if within_minutes else None
    with _LOCK:
        records = [
            item
            for item in _load_state().get("records", [])
            if isinstance(item, dict) and item.get("probe_name") == probe_name
        ]
    if cutoff:
        records = [
            item
            for item in records
            if (ts := _parse_ts(item.get("timestamp"))) is not None and ts >= cutoff
        ]
    records.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    return records[:limit]


def last_seen_row_at(probe_name: str) -> str | None:
    for record in recent_records(probe_name, limit=500):
        try:
            rowcount = int(record.get("rowcount") or 0)
        except (TypeError, ValueError):
            rowcount = 0
        if rowcount > 0 and record.get("status") == "OK":
            return str(record.get("timestamp"))
    return None


def audit_contract_ok(probe_name: str, *, required_ok: int, within_minutes: int) -> tuple[bool, int]:
    records = recent_records(probe_name, within_minutes=within_minutes, limit=required_ok)
    ok_count = sum(1 for record in records if record.get("status") == "OK")
    return len(records) >= required_ok and ok_count == len(records), ok_count

