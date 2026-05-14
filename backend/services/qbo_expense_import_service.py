"""Manual QuickBooks expense import service.

This stores downloaded QuickBooks Online expense rows as read-only evidence for
FleetPulse analytics. QBO remains the source of truth for financial expenses;
FleetPulse only retains an idempotent reporting projection for cost-per-mile
and cost-per-hour calculations.
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


QBO_EXPENSE_AUTHORITY = "K1 Group LLC / QuickBooks Online expense export"
QBO_EXPENSE_NAMESPACE = "qbo_expense_v1"
_STATE_LOCK = threading.Lock()

_FIELD_ALIASES = {
    "account": "account_name",
    "accountname": "account_name",
    "accountfullname": "account_name",
    "accountingdate": "transaction_date",
    "amount": "amount_usd",
    "category": "category",
    "class": "class_name",
    "date": "transaction_date",
    "debit": "amount_usd",
    "description": "description",
    "docnum": "document_number",
    "expenseamount": "amount_usd",
    "expensecategory": "category",
    "lineamount": "amount_usd",
    "memo": "memo",
    "name": "vendor_name",
    "netamount": "amount_usd",
    "num": "document_number",
    "payee": "vendor_name",
    "posteddate": "transaction_date",
    "split": "category",
    "supplier": "vendor_name",
    "total": "amount_usd",
    "transactiondate": "transaction_date",
    "transactionid": "transaction_id",
    "transactiontype": "transaction_type",
    "txn": "transaction_id",
    "txndate": "transaction_date",
    "txnid": "transaction_id",
    "type": "transaction_type",
    "vendor": "vendor_name",
}

_DEFAULT_INSURANCE_PATTERNS = ("insurance",)
_DEFAULT_EXCLUDED_PATTERNS = (
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


@dataclass(frozen=True)
class QboExpenseRecord:
    id: str
    idempotency_key: str
    transaction_date: str
    amount_usd: float
    account_name: str | None
    category: str | None
    vendor_name: str | None
    memo: str | None
    description: str | None
    transaction_type: str | None
    transaction_id: str | None
    document_number: str | None
    class_name: str | None
    source_filename: str | None
    source_authority: str
    projection_mode: str
    created_at: str
    raw: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ParsedQboExpense:
    row_number: int
    record: QboExpenseRecord


@dataclass(frozen=True)
class QboExpenseImportResult:
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
            "source_authority": QBO_EXPENSE_AUTHORITY,
            "projection_mode": "read_only",
            "dry_run": self.dry_run,
            "total_records": self.total_records,
            "imported_count": self.imported_count,
            "duplicate_count": self.duplicate_count,
            "invalid_count": self.invalid_count,
            "errors": self.errors,
            "summary": self.summary,
        }


class QboExpenseStateStore:
    def __init__(self, path: Path | str | None = None, retained_record_limit: int | None = None):
        self.path = Path(path) if path else _state_path_from_env()
        self.retained_record_limit = retained_record_limit or _retained_record_limit_from_env()

    def _empty_state(self) -> dict[str, Any]:
        return {
            "version": 1,
            "processed_idempotency_keys": [],
            "rows": [],
            "coverage_start": None,
            "coverage_end": None,
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
            raise RuntimeError("qbo_expense_state_invalid")
        payload.setdefault("processed_idempotency_keys", [])
        payload.setdefault("rows", [])
        payload.setdefault("coverage_start", None)
        payload.setdefault("coverage_end", None)
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
        rows.sort(key=lambda item: str(item.get("transaction_date") or ""), reverse=True)
        return rows

    def state_metadata(self) -> dict[str, Any]:
        with _STATE_LOCK:
            state = self.load_state()
        return {
            "coverage_start": state.get("coverage_start"),
            "coverage_end": state.get("coverage_end"),
            "last_imported_at": state.get("last_imported_at"),
        }

    def append_records(
        self,
        parsed_records: list[ParsedQboExpense],
        *,
        dry_run: bool = False,
        coverage_start: date | None = None,
        coverage_end: date | None = None,
    ) -> tuple[int, int, list[QboExpenseRecord]]:
        with _STATE_LOCK:
            state = self.load_state()
            processed_keys = [str(key) for key in state.get("processed_idempotency_keys", [])]
            processed = set(processed_keys)
            existing_rows = [row for row in state.get("rows", []) if isinstance(row, dict)]
            imported = 0
            duplicates = 0
            accepted: list[QboExpenseRecord] = []

            for parsed in parsed_records:
                key = parsed.record.idempotency_key
                if key in processed:
                    duplicates += 1
                    continue
                imported += 1
                accepted.append(parsed.record)
                if not dry_run:
                    processed.add(key)
                    processed_keys.append(key)
                    existing_rows.append(parsed.record.as_dict())

            if not dry_run:
                existing_rows.sort(
                    key=lambda item: str(item.get("transaction_date") or ""),
                    reverse=True,
                )
                state["rows"] = existing_rows[: self.retained_record_limit]
                state["processed_idempotency_keys"] = processed_keys[
                    -self.retained_record_limit * 2 :
                ]
                if coverage_start:
                    state["coverage_start"] = _min_date_text(
                        state.get("coverage_start"),
                        coverage_start.isoformat(),
                    )
                if coverage_end:
                    state["coverage_end"] = _max_date_text(
                        state.get("coverage_end"),
                        coverage_end.isoformat(),
                    )
                state["last_imported_at"] = datetime.now(timezone.utc).isoformat()
                self.save_state(state)

            return imported, duplicates, accepted


def import_qbo_expenses(
    content: str,
    *,
    filename: str | None = None,
    dry_run: bool = False,
    period_start: date | datetime | str | None = None,
    period_end: date | datetime | str | None = None,
    store: QboExpenseStateStore | None = None,
) -> QboExpenseImportResult:
    store = store or QboExpenseStateStore()
    parsed_rows, errors = parse_qbo_expense_content(content, filename=filename)
    coverage_start = _coerce_date(period_start)
    coverage_end = _coerce_date(period_end)
    if coverage_start and coverage_end and coverage_start > coverage_end:
        raise ValueError("period_start must be on or before period_end")
    imported, duplicates, accepted = store.append_records(
        parsed_rows,
        dry_run=dry_run,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
    )
    invalid_count = len(errors)
    status = "ok" if imported or duplicates or not invalid_count else "invalid"
    return QboExpenseImportResult(
        status=status,
        dry_run=dry_run,
        total_records=len(parsed_rows) + invalid_count,
        imported_count=imported,
        duplicate_count=duplicates,
        invalid_count=invalid_count,
        errors=errors,
        summary=summarize_qbo_expenses([record.as_dict() for record in accepted]),
    )


def parse_qbo_expense_content(
    content: str,
    *,
    filename: str | None = None,
) -> tuple[list[ParsedQboExpense], list[str]]:
    rows = _load_export_rows(content, filename)
    parsed: list[ParsedQboExpense] = []
    errors: list[str] = []
    created_at = datetime.now(timezone.utc).isoformat()

    for index, raw_row in enumerate(rows, start=1):
        try:
            record = _record_from_row(raw_row, index, filename, created_at)
        except ValueError as exc:
            if str(exc).endswith("skipped non-transaction row"):
                continue
            errors.append(str(exc))
            continue
        parsed.append(ParsedQboExpense(row_number=index, record=record))

    return parsed, errors


def get_qbo_expense_summary(
    days: int = 370,
    *,
    store: QboExpenseStateStore | None = None,
) -> dict[str, Any]:
    store = store or QboExpenseStateStore()
    records = _filter_records_by_days(store.rows(), days)
    return {
        "source_authority": QBO_EXPENSE_AUTHORITY,
        "projection_mode": "read_only",
        "period_days": days,
        **store.state_metadata(),
        **summarize_qbo_expenses(records),
    }


def get_qbo_expense_transactions(
    limit: int = 100,
    *,
    store: QboExpenseStateStore | None = None,
) -> dict[str, Any]:
    safe_limit = min(max(int(limit or 100), 1), 500)
    store = store or QboExpenseStateStore()
    return {
        "source_authority": QBO_EXPENSE_AUTHORITY,
        "projection_mode": "read_only",
        **store.state_metadata(),
        "records": store.rows()[:safe_limit],
    }


def qbo_expense_import_status() -> dict[str, Any]:
    api_key_required = bool(os.getenv("FLEETPULSE_QBO_EXPENSE_IMPORT_API_KEY", "").strip())
    path = _state_path_from_env()
    return {
        "source_authority": QBO_EXPENSE_AUTHORITY,
        "projection_mode": "read_only",
        "api_key_required": api_key_required,
        "state_path_configured": bool(_configured_state_path_text()),
        "state_exists": path.exists(),
        "missing_config": [] if _configured_state_path_text() else ["FLEETPULSE_QBO_EXPENSE_STATE_PATH"],
    }


def validate_qbo_expense_import_api_key(provided: str | None) -> None:
    expected = os.getenv("FLEETPULSE_QBO_EXPENSE_IMPORT_API_KEY", "").strip()
    if expected and provided != expected:
        raise PermissionError("Invalid QBO expense import API key")


def summarize_qbo_expenses(records: list[dict[str, Any]]) -> dict[str, Any]:
    insurance_total = 0.0
    other_total = 0.0
    excluded_count = 0
    included_count = 0
    dates: list[str] = []

    for record in records:
        day = _date_key(record.get("transaction_date"))
        if day:
            dates.append(day)
        bucket = _expense_bucket(record)
        if bucket is None:
            excluded_count += 1
            continue
        included_count += 1
        if bucket == "insurance":
            insurance_total += _number(record.get("amount_usd"))
        else:
            other_total += _number(record.get("amount_usd"))

    return {
        "row_count": len(records),
        "included_expense_count": included_count,
        "excluded_expense_count": excluded_count,
        "insurance_total": round(insurance_total, 2),
        "other_expense_total": round(other_total, 2),
        "included_expense_total": round(insurance_total + other_total, 2),
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
    }


def _state_path_from_env() -> Path:
    configured = _configured_state_path_text()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "data" / "qbo_expenses.json"


def _configured_state_path_text() -> str:
    return (
        os.getenv("FLEETPULSE_QBO_EXPENSE_STATE_PATH", "").strip()
        or os.getenv("FLEETPULSE_QBO_EXPENSE_FEED_PATH", "").strip()
        or os.getenv("FLEETPULSE_QBO_FINANCIAL_FEED_PATH", "").strip()
    )


def _retained_record_limit_from_env() -> int:
    try:
        return max(int(os.getenv("FLEETPULSE_QBO_EXPENSE_RETAINED_RECORDS", "50000")), 1)
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
            for key in ("rows", "expenses", "transactions", "data", "items", "value"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [row for row in value if isinstance(row, dict)]
            return [payload]
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in sample else csv.excel
    return [
        dict(row)
        for row in csv.DictReader(io.StringIO(text), dialect=dialect)
        if any(str(value or "").strip() for value in row.values())
    ]


def _record_from_row(
    raw_row: dict[str, Any],
    row_number: int,
    filename: str | None,
    created_at: str,
) -> QboExpenseRecord:
    row = _canonicalize_row(raw_row)
    transaction_date = _parse_date_string(row.get("transaction_date"))
    if not transaction_date:
        if _row_has_money(row):
            raise ValueError(f"row {row_number}: missing QBO transaction date")
        raise ValueError(f"row {row_number}: skipped non-transaction row")

    amount = _parse_number(row.get("amount_usd"))
    if amount is None:
        raise ValueError(f"row {row_number}: missing QBO expense amount")

    account_name = _clean_text(row.get("account_name"))
    category = _clean_text(row.get("category"))
    vendor_name = _clean_text(row.get("vendor_name"))
    memo = _clean_text(row.get("memo"))
    description = _clean_text(row.get("description"))
    transaction_type = _clean_text(row.get("transaction_type"))
    transaction_id = _clean_text(row.get("transaction_id"))
    document_number = _clean_text(row.get("document_number"))

    idempotency_key = stable_idempotency_key(
        QBO_EXPENSE_NAMESPACE,
        transaction_id,
        document_number,
        transaction_date,
        account_name,
        category,
        vendor_name,
        round(amount, 2),
        memo or description,
    )

    return QboExpenseRecord(
        id=idempotency_key,
        idempotency_key=idempotency_key,
        transaction_date=transaction_date,
        amount_usd=round(abs(amount), 2),
        account_name=account_name,
        category=category,
        vendor_name=vendor_name,
        memo=memo,
        description=description,
        transaction_type=transaction_type,
        transaction_id=transaction_id,
        document_number=document_number,
        class_name=_clean_text(row.get("class_name")),
        source_filename=filename,
        source_authority=QBO_EXPENSE_AUTHORITY,
        projection_mode="read_only",
        created_at=created_at,
        raw=_redact_raw_row(raw_row),
    )


def _canonicalize_row(row: dict[str, Any]) -> dict[str, Any]:
    canonical: dict[str, Any] = {}
    for key, value in row.items():
        normalized = _normalize_header(key)
        canonical_key = _FIELD_ALIASES.get(normalized, normalized)
        if canonical_key not in canonical or not canonical.get(canonical_key):
            canonical[canonical_key] = _clean_text(value)
    return canonical


def _normalize_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = text.replace("$", "").replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    number = float(match.group(0))
    return -abs(number) if negative else number


def _number(value: Any) -> float:
    parsed = _parse_number(value)
    return float(parsed or 0)


def _parse_date_string(value: Any) -> str | None:
    parsed = _coerce_date(value)
    return parsed.isoformat() if parsed else None


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
    token = text.split()[0]
    try:
        return datetime.fromisoformat(token.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in (
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d",
        "%m-%d-%Y",
        "%m-%d-%y",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%y %H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _redact_raw_row(row: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in row.items():
        normalized = _normalize_header(key)
        if any(token in normalized for token in ("accountnumber", "routing", "card")):
            redacted[str(key)] = "****"
        else:
            redacted[str(key)] = value
    return redacted


def _filter_records_by_days(records: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    safe_days = min(max(int(days or 370), 1), 370)
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=safe_days)
    filtered = []
    for record in records:
        key = _date_key(record.get("transaction_date"))
        if not key:
            continue
        try:
            if date.fromisoformat(key) >= cutoff:
                filtered.append(record)
        except ValueError:
            continue
    return filtered


def _date_key(value: Any) -> str | None:
    parsed = _parse_date_string(value)
    return parsed[:10] if parsed else None


def _row_has_money(row: dict[str, Any]) -> bool:
    return _parse_number(row.get("amount_usd")) is not None


def _expense_bucket(record: dict[str, Any]) -> str | None:
    haystack = " ".join(
        str(record.get(name) or "")
        for name in (
            "account_name",
            "category",
            "vendor_name",
            "memo",
            "description",
            "transaction_type",
        )
    ).casefold()
    if any(pattern in haystack for pattern in _DEFAULT_EXCLUDED_PATTERNS):
        return None
    if any(pattern in haystack for pattern in _DEFAULT_INSURANCE_PATTERNS):
        return "insurance"
    return "other"


def _min_date_text(current: Any, candidate: str) -> str:
    values = [value for value in (str(current or "").strip(), candidate) if value]
    return min(values)


def _max_date_text(current: Any, candidate: str) -> str:
    values = [value for value in (str(current or "").strip(), candidate) if value]
    return max(values)
