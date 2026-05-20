"""Scheduled QuickBooks financial snapshot import.

FleetPulse stores QBO report/API output as read-only evidence for Tower and
operating-cost dashboards. QuickBooks remains the financial source of truth;
this module only replaces the local scheduled-feed snapshot used by APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from services.qbo_financial_snapshot_service import (
    QBO_FINANCIAL_AUTHORITY,
    QboFinancialConfig,
    build_qbo_financial_snapshot_from_content,
)


DEFAULT_QBO_FINANCIAL_STATE_PATH = "/home/data/fleetpulse_qbo_financial.json"


@dataclass(frozen=True)
class QboFinancialFeedImportResult:
    status: str
    dry_run: bool
    row_count: int
    invalid_count: int
    errors: list[str]
    state_path: str
    summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_authority": QBO_FINANCIAL_AUTHORITY,
            "projection_mode": "read_only",
            "dry_run": self.dry_run,
            "row_count": self.row_count,
            "invalid_count": self.invalid_count,
            "errors": self.errors,
            "state_path": self.state_path,
            "summary": self.summary,
        }


class QboFinancialFeedStateStore:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else _state_path_from_env()

    def save_snapshot(self, payload: dict[str, Any], *, dry_run: bool = False) -> None:
        if dry_run:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp_path.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        tmp_path.replace(self.path)

    def status(self) -> dict[str, Any]:
        configured = bool(_configured_state_path_text())
        if not self.path.exists():
            return {
                "source_authority": QBO_FINANCIAL_AUTHORITY,
                "projection_mode": "read_only",
                "status": "awaiting_feed",
                "state_path": str(self.path),
                "state_path_configured": configured,
                "missing_config": [] if configured else ["FLEETPULSE_QBO_FINANCIAL_STATE_PATH"],
                "row_count": 0,
                "last_imported_at": None,
                "coverage_start": None,
                "coverage_end": None,
            }
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        rows = payload.get("rows") if isinstance(payload, dict) else payload if isinstance(payload, list) else []
        row_count = len([row for row in rows if isinstance(row, dict)])
        return {
            "source_authority": QBO_FINANCIAL_AUTHORITY,
            "projection_mode": "read_only",
            "status": "healthy" if row_count else "awaiting_feed",
            "state_path": str(self.path),
            "state_path_configured": configured,
            "missing_config": [] if configured else ["FLEETPULSE_QBO_FINANCIAL_STATE_PATH"],
            "row_count": row_count,
            "last_imported_at": payload.get("last_imported_at") if isinstance(payload, dict) else None,
            "coverage_start": payload.get("coverage_start") if isinstance(payload, dict) else None,
            "coverage_end": payload.get("coverage_end") if isinstance(payload, dict) else None,
        }


def import_qbo_financial_feed(
    content: str,
    *,
    filename: str | None = None,
    dry_run: bool = False,
    period_start: date | datetime | str | None = None,
    period_end: date | datetime | str | None = None,
    store: QboFinancialFeedStateStore | None = None,
) -> QboFinancialFeedImportResult:
    store = store or QboFinancialFeedStateStore()
    errors: list[str] = []
    try:
        snapshot = build_qbo_financial_snapshot_from_content(
            content,
            filename=filename,
            start=period_start,
            end=period_end,
            config=QboFinancialConfig(),
            include_records=True,
        )
    except Exception as exc:
        errors.append(str(exc))
        return QboFinancialFeedImportResult(
            status="invalid",
            dry_run=dry_run,
            row_count=0,
            invalid_count=1,
            errors=errors,
            state_path=str(store.path),
            summary={},
        )

    row_count = int(snapshot.get("row_count") or 0)
    if row_count <= 0:
        errors.append("qbo_financial_feed_contains_no_rows")
        return QboFinancialFeedImportResult(
            status="invalid",
            dry_run=dry_run,
            row_count=0,
            invalid_count=1,
            errors=errors,
            state_path=str(store.path),
            summary=_summary_from_snapshot(snapshot),
        )

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "version": 1,
        "source_authority": QBO_FINANCIAL_AUTHORITY,
        "projection_mode": "read_only",
        "coverage_start": _date_text(period_start) or snapshot.get("coverage_start"),
        "coverage_end": _date_text(period_end) or snapshot.get("coverage_end"),
        "last_imported_at": now,
        "rows": snapshot.get("rows") or [],
        "summary": _summary_from_snapshot(snapshot),
    }
    if payload["coverage_start"] is None:
        payload.pop("coverage_start")
    if payload["coverage_end"] is None:
        payload.pop("coverage_end")
    store.save_snapshot(payload, dry_run=dry_run)

    return QboFinancialFeedImportResult(
        status="ok",
        dry_run=dry_run,
        row_count=row_count,
        invalid_count=0,
        errors=[],
        state_path=str(store.path),
        summary=payload["summary"],
    )


def qbo_financial_feed_status(
    *,
    store: QboFinancialFeedStateStore | None = None,
) -> dict[str, Any]:
    return (store or QboFinancialFeedStateStore()).status()


def validate_qbo_financial_import_api_key(provided: str | None) -> None:
    expected = (
        os.getenv("FLEETPULSE_QBO_FINANCIAL_IMPORT_API_KEY", "").strip()
        or os.getenv("FLEETPULSE_QBO_EXPENSE_IMPORT_API_KEY", "").strip()
    )
    if expected and provided != expected:
        raise PermissionError("Invalid QBO financial import API key")


def _summary_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": snapshot.get("status"),
        "message": snapshot.get("message"),
        "accounts_payable": snapshot.get("accounts_payable") or {},
        "accounts_receivable": snapshot.get("accounts_receivable") or [],
        "cash_flow": snapshot.get("cash_flow") or {},
        "expense_summary": snapshot.get("expense_summary") or {},
    }


def _configured_state_path_text() -> str:
    return (
        os.getenv("FLEETPULSE_QBO_FINANCIAL_STATE_PATH", "").strip()
        or os.getenv("FLEETPULSE_QBO_FINANCIAL_FEED_PATH", "").strip()
    )


def _state_path_from_env() -> Path:
    return Path(_configured_state_path_text() or DEFAULT_QBO_FINANCIAL_STATE_PATH)


def _date_text(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip() or None
