"""Read-only QuickBooks financial snapshots for Control Tower and cost rollups.

QuickBooks remains the financial source of truth. This module only normalizes
configured QBO report/API evidence into dashboard-ready AP, AR, and K1 Logistics
expense projections. It never creates or updates QuickBooks records.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx


QBO_FINANCIAL_AUTHORITY = "QuickBooks Online financial snapshot"
QBO_K1L_EXPENSE_AUTHORITY = "K1 Logistics Inc / QuickBooks Online expenses"
AR_BUCKETS = ("0-30", "31-60", "61-90", "90+")

_FIELD_ALIASES = {
    "account": "account_name",
    "accountname": "account_name",
    "accountfullname": "account_name",
    "amount": "amount",
    "balance": "balance",
    "class": "class_name",
    "classname": "class_name",
    "customer": "customer_name",
    "customer_name": "customer_name",
    "customername": "customer_name",
    "date": "transaction_date",
    "department": "department_name",
    "department_name": "department_name",
    "departmentname": "department_name",
    "description": "description",
    "docnum": "document_number",
    "duedate": "due_date",
    "entity": "entity_name",
    "entity_name": "entity_name",
    "entityname": "entity_name",
    "location": "location_name",
    "location_name": "location_name",
    "locationname": "location_name",
    "memo": "memo",
    "name": "entity_name",
    "openbalance": "balance",
    "openbalanceamount": "balance",
    "posteddate": "transaction_date",
    "qborowkind": "qbo_row_kind",
    "supplier": "vendor_name",
    "total": "amount",
    "totalamt": "amount",
    "transactiondate": "transaction_date",
    "transaction_date": "transaction_date",
    "transactionid": "transaction_id",
    "transaction_id": "transaction_id",
    "transactiontype": "transaction_type",
    "transaction_type": "transaction_type",
    "txn": "transaction_id",
    "txndate": "transaction_date",
    "txnid": "transaction_id",
    "type": "transaction_type",
    "vendor": "vendor_name",
    "vendor_name": "vendor_name",
    "vendorname": "vendor_name",
}

_DEFAULT_K1L_PATTERNS = (
    "k1 logistics",
    "k1 logistics inc",
    "k1 logistics, inc",
)
_DEFAULT_INSURANCE_PATTERNS = ("insurance",)
QBO_K1L_COST_BUCKETS = (
    "maintenance",
    "fuel",
    "insurance",
    "employee",
    "rental_trucks_trailers",
)
_EMPLOYEE_PATTERNS = (
    "employee",
    "company contributions",
    "health insurance",
    "payroll",
    "pre-employment",
    "salary",
    "salaries",
    "wages",
    "worker",
)
_RENTAL_TRUCK_TRAILER_PATTERNS = (
    "bruckner",
    "camarena",
    "equipment rental",
    "equipment rental - cogs",
    "idlease",
    "idealease",
    "ryder",
    "truck lease",
    "trucks/trailers lease",
    "trailer lease",
    "truck rental",
    "trailer rental",
    "xtra",
    "xtra lease",
)
_MAINTENANCE_PATTERNS = (
    "2290",
    "highway used tax",
    "ifta",
    "parking",
    "permit",
    "permits",
    "repair",
    "maintenance",
    "road services",
    "safety compliance",
    "registration",
    "registrations",
    "toll",
    "tolls",
    "towing",
    "license",
    "licenses",
    "truck wash",
    "vehicle registration",
    "vehicle wash",
)
_FUEL_PATTERNS = (
    "diesel",
    "fuel",
    "fuel - cost",
    "gas & fuel",
    "vehicle gas",
    "vehicle gas & fuel",
)
_DEFAULT_EXCLUDED_EXPENSE_PATTERNS = (
    "accounts payable",
    "accounts receivable",
    "brokerage commission",
    "carrier",
    "commissions & fees",
    "contractor",
    "driver pay",
    "driver settlement",
    "factoring",
    "income",
    "revenue",
    "sales",
)


@dataclass(frozen=True)
class QboFinancialConfig:
    """Runtime settings for a read-only QuickBooks financial projection."""

    feed_url: str = ""
    feed_path: str = ""
    api_key: str = ""
    api_key_header: str = "X-FleetPulse-QBO-Key"
    timeout_seconds: float = 30.0
    live_enabled: bool = False
    company_id: str = ""
    access_token: str = ""
    base_url: str = "https://quickbooks.api.intuit.com"
    minor_version: str = "75"
    k1l_entity_patterns: tuple[str, ...] = _DEFAULT_K1L_PATTERNS
    insurance_patterns: tuple[str, ...] = _DEFAULT_INSURANCE_PATTERNS
    excluded_expense_patterns: tuple[str, ...] = _DEFAULT_EXCLUDED_EXPENSE_PATTERNS

    @classmethod
    def from_env(cls) -> "QboFinancialConfig":
        return cls(
            feed_url=os.getenv("FLEETPULSE_QBO_FINANCIAL_FEED_URL", "").strip(),
            feed_path=(
                os.getenv("FLEETPULSE_QBO_FINANCIAL_FEED_PATH", "").strip()
                or os.getenv("FLEETPULSE_QBO_FINANCIAL_STATE_PATH", "").strip()
                or os.getenv("FLEETPULSE_QBO_EXPENSE_STATE_PATH", "").strip()
            ),
            api_key=(
                os.getenv("FLEETPULSE_QBO_FINANCIAL_FEED_API_KEY", "").strip()
                or os.getenv("FLEETPULSE_QBO_EXPENSE_FEED_API_KEY", "").strip()
            ),
            api_key_header=(
                os.getenv(
                    "FLEETPULSE_QBO_FINANCIAL_FEED_API_KEY_HEADER",
                    os.getenv("FLEETPULSE_QBO_EXPENSE_FEED_API_KEY_HEADER", "X-FleetPulse-QBO-Key"),
                ).strip()
                or "X-FleetPulse-QBO-Key"
            ),
            timeout_seconds=_float_env("FLEETPULSE_QBO_FINANCIAL_TIMEOUT_SECONDS", 30.0),
            live_enabled=_bool_env("FLEETPULSE_QBO_LIVE_ENABLED", False),
            company_id=(
                os.getenv("FLEETPULSE_QBO_COMPANY_ID", "").strip()
                or os.getenv("QBO_COMPANY_ID", "").strip()
            ),
            access_token=(
                os.getenv("FLEETPULSE_QBO_ACCESS_TOKEN", "").strip()
                or os.getenv("QBO_ACCESS_TOKEN", "").strip()
            ),
            base_url=(
                os.getenv("FLEETPULSE_QBO_BASE_URL", "").strip()
                or "https://quickbooks.api.intuit.com"
            ).rstrip("/"),
            minor_version=os.getenv("FLEETPULSE_QBO_MINOR_VERSION", "75").strip() or "75",
            k1l_entity_patterns=_csv_env(
                "FLEETPULSE_QBO_K1L_ENTITY_PATTERNS",
                ",".join(_DEFAULT_K1L_PATTERNS),
            ),
            insurance_patterns=_csv_env("FLEETPULSE_QBO_INSURANCE_ACCOUNT_PATTERNS", "insurance"),
            excluded_expense_patterns=_csv_env(
                "FLEETPULSE_QBO_EXCLUDED_ACCOUNT_PATTERNS",
                ",".join(_DEFAULT_EXCLUDED_EXPENSE_PATTERNS),
            ),
        )

    @property
    def feed_configured(self) -> bool:
        return bool(self.feed_url or self.feed_path)

    @property
    def live_configured(self) -> bool:
        return bool(self.live_enabled and self.company_id and self.access_token)

    @property
    def configured(self) -> bool:
        return self.feed_configured or self.live_enabled


def get_qbo_financial_snapshot(
    *,
    start: date | datetime | str | None = None,
    end: date | datetime | str | None = None,
    config: QboFinancialConfig | None = None,
    today: date | None = None,
    include_records: bool = False,
) -> dict[str, Any]:
    """Return AP, AR, and K1L expense evidence from the configured QBO source."""

    config = config or QboFinancialConfig.from_env()
    as_of = today or datetime.now(timezone.utc).date()
    period_start = _coerce_date(start)
    period_end = _coerce_date(end) or as_of
    if period_start and period_start > period_end:
        raise ValueError("start must be on or before end")

    if not config.configured:
        return _empty_snapshot(
            "awaiting_feed",
            "QuickBooks financial feed or live QBO credentials are not configured.",
            missing_config=["FLEETPULSE_QBO_FINANCIAL_FEED_URL"],
        )
    if config.live_enabled and not config.live_configured and not config.feed_configured:
        return _empty_snapshot(
            "awaiting_feed",
            "FLEETPULSE_QBO_LIVE_ENABLED is true, but company ID and access token are not configured.",
            missing_config=["FLEETPULSE_QBO_COMPANY_ID", "FLEETPULSE_QBO_ACCESS_TOKEN"],
        )

    try:
        raw_rows, metadata = _load_rows(config, start=period_start, end=period_end)
    except Exception as exc:
        return _empty_snapshot(
            "unavailable",
            f"QuickBooks financial snapshot unavailable: {type(exc).__name__}",
            missing_config=[],
        )

    return build_qbo_financial_snapshot_from_rows(
        raw_rows,
        metadata=metadata,
        start=period_start,
        end=period_end,
        config=config,
        today=as_of,
        include_records=include_records,
    )


def build_qbo_financial_snapshot_from_content(
    content: str,
    *,
    filename: str | None = None,
    start: date | datetime | str | None = None,
    end: date | datetime | str | None = None,
    config: QboFinancialConfig | None = None,
    today: date | None = None,
    include_records: bool = False,
) -> dict[str, Any]:
    """Normalize supplied QBO report/export content without reading live QBO."""

    period_start = _coerce_date(start)
    period_end = _coerce_date(end) or today or datetime.now(timezone.utc).date()
    if period_start and period_start > period_end:
        raise ValueError("start must be on or before end")
    raw_rows, metadata = _coerce_rows(content, _content_type_from_filename(filename))
    return build_qbo_financial_snapshot_from_rows(
        raw_rows,
        metadata=metadata,
        start=period_start,
        end=period_end,
        config=config or QboFinancialConfig(),
        today=today,
        include_records=include_records,
    )


def build_qbo_financial_snapshot_from_rows(
    raw_rows: list[dict[str, Any]],
    *,
    metadata: dict[str, Any] | None = None,
    start: date | datetime | str | None = None,
    end: date | datetime | str | None = None,
    config: QboFinancialConfig | None = None,
    today: date | None = None,
    include_records: bool = False,
) -> dict[str, Any]:
    """Return AP/AR/K1L expense projection from already-loaded QBO rows."""

    metadata = metadata or {}
    config = config or QboFinancialConfig()
    as_of = today or datetime.now(timezone.utc).date()
    period_start = _coerce_date(start)
    period_end = _coerce_date(end) or as_of
    if period_start and period_start > period_end:
        raise ValueError("start must be on or before end")

    canonical_rows = [_canonicalize_row(row) for row in raw_rows]
    ap = _accounts_payable_summary(canonical_rows, today=as_of)
    ar_buckets = _accounts_receivable_buckets(canonical_rows, today=as_of)
    expense_rows = _k1l_expense_rows(
        canonical_rows,
        config=config,
        start=period_start,
        end=period_end,
    )
    expense_totals = _expense_totals_by_bucket(expense_rows)
    expense_total = round(sum(_number(row.get("Amount")) for row in expense_rows), 2)
    expense_total_value: float | None = expense_total if expense_rows else None
    source_row_count = len(canonical_rows)

    status = "healthy" if source_row_count else "awaiting_feed"
    if source_row_count and not expense_rows:
        status = "partial"
    message = (
        f"Read {source_row_count} QBO financial row(s); "
        f"{ap['pending_bills']} open AP bill(s), "
        f"{sum(bucket['count'] for bucket in ar_buckets)} open AR row(s), "
        f"{len(expense_rows)} K1L expense row(s)."
    )
    if not source_row_count:
        message = "QuickBooks financial source is configured, but no AP/AR/expense rows were returned."

    snapshot: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "projection_mode": "read_only",
        "source_authority": QBO_FINANCIAL_AUTHORITY,
        "expense_source_authority": QBO_K1L_EXPENSE_AUTHORITY,
        "status": status,
        "message": message,
        "missing_config": [],
        "source_mode": metadata.get("source_mode") or ("live_qbo" if config.live_configured else "feed"),
        "row_count": source_row_count,
        "accounts_payable": ap,
        "accounts_receivable": ar_buckets,
        "cash_flow": {
            "bank_balance": None,
            "net_weekly": None,
            "weekly_income": None,
            "weekly_expenses": None,
            "k1l_expense_total": expense_total_value,
        },
        "expense_summary": {
            "k1l_expense_total": expense_total_value,
            "k1l_expense_count": len(expense_rows),
            "category_totals": expense_totals if expense_rows else {},
            "maintenance_total": expense_totals.get("maintenance") if expense_rows else None,
            "fuel_total": expense_totals.get("fuel") if expense_rows else None,
            "insurance_total": expense_totals.get("insurance") if expense_rows else None,
            "employee_total": expense_totals.get("employee") if expense_rows else None,
            "rental_trucks_trailers_total": expense_totals.get("rental_trucks_trailers") if expense_rows else None,
            "other_expense_total": (
                round(
                    expense_totals.get("maintenance", 0.0)
                    + expense_totals.get("fuel", 0.0)
                    + expense_totals.get("employee", 0.0)
                    + expense_totals.get("rental_trucks_trailers", 0.0),
                    2,
                )
                if expense_rows
                else None
            ),
        },
        "coverage_start": metadata.get("coverage_start"),
        "coverage_end": metadata.get("coverage_end"),
        "last_updated": metadata.get("last_updated") or metadata.get("last_imported_at"),
    }
    if include_records:
        snapshot["rows"] = canonical_rows
        snapshot["expense_rows"] = expense_rows
    return snapshot


def load_qbo_k1l_expense_rows(
    *,
    config: QboFinancialConfig | None = None,
    start: date | datetime | str | None = None,
    end: date | datetime | str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return QBO K1L expense rows in the shape expected by operating cost code."""

    snapshot = get_qbo_financial_snapshot(
        start=start,
        end=end,
        config=config,
        include_records=True,
    )
    return list(snapshot.get("expense_rows") or []), {
        "coverage_start": snapshot.get("coverage_start"),
        "coverage_end": snapshot.get("coverage_end"),
        "last_imported_at": snapshot.get("last_updated"),
        "source_status": snapshot.get("status"),
        "source_message": snapshot.get("message"),
        "source_authority": snapshot.get("expense_source_authority") or QBO_K1L_EXPENSE_AUTHORITY,
        "source_row_count": snapshot.get("row_count") or 0,
    }


def _expense_totals_by_bucket(expense_rows: list[dict[str, Any]]) -> dict[str, float]:
    totals = {bucket: 0.0 for bucket in QBO_K1L_COST_BUCKETS}
    for row in expense_rows:
        bucket = str(row.get("qbo_expense_bucket") or "")
        if bucket in totals:
            totals[bucket] += _number(row.get("Amount"))
    return {bucket: round(total, 2) for bucket, total in totals.items()}


def _empty_snapshot(status: str, message: str, *, missing_config: list[str]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "projection_mode": "read_only",
        "source_authority": QBO_FINANCIAL_AUTHORITY,
        "expense_source_authority": QBO_K1L_EXPENSE_AUTHORITY,
        "status": status,
        "message": message,
        "missing_config": missing_config,
        "source_mode": "unconfigured",
        "row_count": 0,
        "accounts_payable": {
            "pending_amount": None,
            "pending_bills": 0,
            "overdue_amount": None,
            "overdue_count": 0,
            "total": None,
        },
        "accounts_receivable": [{"bucket": bucket, "amount": None, "count": 0} for bucket in AR_BUCKETS],
        "cash_flow": {
            "bank_balance": None,
            "net_weekly": None,
            "weekly_income": None,
            "weekly_expenses": None,
            "k1l_expense_total": None,
        },
        "expense_summary": {
            "k1l_expense_total": None,
            "k1l_expense_count": 0,
            "category_totals": {},
            "maintenance_total": None,
            "fuel_total": None,
            "insurance_total": None,
            "employee_total": None,
            "rental_trucks_trailers_total": None,
            "other_expense_total": None,
        },
        "coverage_start": None,
        "coverage_end": None,
        "last_updated": None,
    }


def _load_rows(
    config: QboFinancialConfig,
    *,
    start: date | None,
    end: date,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if config.feed_url:
        headers = {"Accept": "application/json,text/csv"}
        if config.api_key:
            headers[config.api_key_header] = config.api_key
        url = _feed_url_with_window(config.feed_url, start=start, end=end)
        with httpx.Client(timeout=config.timeout_seconds) as client:
            response = client.get(url, headers=headers)
        response.raise_for_status()
        rows, metadata = _coerce_rows(response.text, response.headers.get("content-type", ""))
        metadata.setdefault("source_mode", "feed_url")
        return rows, metadata
    if config.feed_path:
        path = Path(config.feed_path)
        if not path.exists():
            return [], {"source_mode": "feed_path"}
        rows, metadata = _coerce_rows(path.read_text(encoding="utf-8-sig"), "")
        metadata.setdefault("source_mode", "feed_path")
        return rows, metadata
    if config.live_configured:
        return _load_live_qbo_rows(config, start=start, end=end)
    return [], {}


def _feed_url_with_window(url: str, *, start: date | None, end: date | None) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if start:
        query["start"] = start.isoformat()
    if end:
        query["end"] = end.isoformat()
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _content_type_from_filename(filename: str | None) -> str:
    suffix = Path(str(filename or "")).suffix.casefold()
    if suffix == ".json":
        return "application/json"
    if suffix in {".csv", ".tsv", ".txt"}:
        return "text/csv"
    return ""


def _load_live_qbo_rows(
    config: QboFinancialConfig,
    *,
    start: date | None,
    end: date,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    start_date = (start or date(end.year, 1, 1)).isoformat()
    end_date = end.isoformat()
    bill_query = (
        "SELECT * FROM Bill "
        f"WHERE Balance > '0' AND TxnDate >= '{start_date}' AND TxnDate <= '{end_date}' "
        "MAXRESULTS 1000"
    )
    invoice_query = (
        "SELECT * FROM Invoice "
        f"WHERE Balance > '0' AND TxnDate >= '{start_date}' AND TxnDate <= '{end_date}' "
        "MAXRESULTS 1000"
    )
    purchase_query = (
        "SELECT * FROM Purchase "
        f"WHERE TxnDate >= '{start_date}' AND TxnDate <= '{end_date}' "
        "MAXRESULTS 1000"
    )
    rows: list[dict[str, Any]] = []
    rows.extend(_qbo_query(config, bill_query, entity_name="Bill"))
    rows.extend(_qbo_query(config, invoice_query, entity_name="Invoice"))
    rows.extend(_qbo_query(config, purchase_query, entity_name="Purchase"))
    return rows, {"source_mode": "live_qbo"}


def _qbo_query(config: QboFinancialConfig, query: str, *, entity_name: str) -> list[dict[str, Any]]:
    url = f"{config.base_url}/v3/company/{config.company_id}/query"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {config.access_token}",
    }
    params = {"query": query, "minorversion": config.minor_version}
    with httpx.Client(timeout=config.timeout_seconds) as client:
        response = client.get(url, headers=headers, params=params)
    response.raise_for_status()
    payload = response.json()
    query_response = payload.get("QueryResponse") if isinstance(payload, dict) else {}
    items = query_response.get(entity_name) if isinstance(query_response, dict) else None
    if not isinstance(items, list):
        return []
    return [_qbo_entity_to_row(item, entity_name) for item in items if isinstance(item, dict)]


def _qbo_entity_to_row(item: dict[str, Any], entity_name: str) -> dict[str, Any]:
    row = {
        "transaction_type": entity_name,
        "transaction_id": item.get("Id"),
        "transaction_date": item.get("TxnDate"),
        "due_date": item.get("DueDate"),
        "amount": item.get("TotalAmt"),
        "balance": item.get("Balance"),
        "entity_name": _ref_name(item.get("VendorRef")) or _ref_name(item.get("CustomerRef")),
        "raw": item,
    }
    if entity_name == "Purchase":
        row["balance"] = item.get("TotalAmt")
    return row


def _ref_name(value: Any) -> str | None:
    if isinstance(value, dict):
        return _clean_text(value.get("name") or value.get("value"))
    return _clean_text(value)


def _coerce_rows(text: str, content_type: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stripped = text.lstrip("\ufeff").strip()
    if not stripped:
        return [], {}
    if "json" in content_type or stripped[:1] in {"[", "{"}:
        payload = json.loads(stripped)
        rows, metadata = _rows_from_json_payload(payload)
        return rows, metadata
    sample = stripped[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in sample else csv.excel
    return (
        [
            dict(row)
            for row in csv.DictReader(io.StringIO(stripped), dialect=dialect)
            if any(str(value or "").strip() for value in row.values())
        ],
        {},
    )


def _rows_from_json_payload(payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)], {}
    if not isinstance(payload, dict):
        return [], {}
    metadata = {
        key: payload.get(key)
        for key in ("coverage_start", "coverage_end", "last_imported_at", "last_updated")
        if payload.get(key)
    }
    rows: list[dict[str, Any]] = []
    for key, row_kind in (
        ("accounts_payable", "ap"),
        ("ap", "ap"),
        ("bills", "ap"),
        ("payables", "ap"),
        ("accounts_receivable", "ar"),
        ("ar", "ar"),
        ("invoices", "ar"),
        ("receivables", "ar"),
        ("expenses", "expense"),
        ("expense_rows", "expense"),
        ("k1l_expenses", "expense"),
        ("k1l_expense_rows", "expense"),
        ("transactions", None),
        ("rows", None),
        ("data", None),
        ("items", None),
        ("value", None),
    ):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    rows.append(_with_row_kind(item, row_kind))
        elif isinstance(value, dict) and key in {"accounts_payable", "ap"}:
            rows.append(_with_row_kind(value, "ap_summary"))
        elif isinstance(value, dict) and key in {"accounts_receivable", "ar"}:
            rows.append(_with_row_kind(value, "ar_summary"))
    if not rows and any(key in payload for key in ("transaction_date", "TxnDate", "Date", "amount", "Amount")):
        rows.append(payload)
    return rows, metadata


def _with_row_kind(row: dict[str, Any], row_kind: str | None) -> dict[str, Any]:
    if not row_kind:
        return row
    enriched = dict(row)
    enriched.setdefault("qbo_row_kind", row_kind)
    return enriched


def _accounts_payable_summary(rows: list[dict[str, Any]], *, today: date) -> dict[str, Any]:
    pending_amount = 0.0
    pending_bills = 0
    overdue_amount = 0.0
    overdue_count = 0
    saw_amount = False
    for row in rows:
        if row.get("qbo_row_kind") == "ap_summary":
            summary = _summary_from_ap_row(row)
            if summary:
                return summary
        if not _is_ap_row(row):
            continue
        amount = _open_amount(row)
        if amount <= 0:
            continue
        saw_amount = True
        pending_amount += amount
        pending_bills += 1
        due_date = _coerce_date(row.get("due_date"))
        if due_date and due_date < today:
            overdue_amount += amount
            overdue_count += 1
    return {
        "pending_amount": round(pending_amount, 2) if saw_amount else None,
        "pending_bills": pending_bills,
        "overdue_amount": round(overdue_amount, 2) if saw_amount else None,
        "overdue_count": overdue_count,
        "total": round(pending_amount, 2) if saw_amount else None,
    }


def _summary_from_ap_row(row: dict[str, Any]) -> dict[str, Any] | None:
    pending_amount = _first_number(row, "pending_amount", "pendingamount", "open_ap", "openap", "total")
    if pending_amount is None:
        return None
    overdue_amount = _first_number(row, "overdue_amount", "overdueamount")
    pending_bills = _first_int(row, "pending_bills", "pendingbills", "count")
    overdue_count = _first_int(row, "overdue_count", "overduecount")
    return {
        "pending_amount": round(pending_amount, 2),
        "pending_bills": pending_bills,
        "overdue_amount": round(overdue_amount or 0.0, 2),
        "overdue_count": overdue_count,
        "total": round(pending_amount, 2),
    }


def _accounts_receivable_buckets(rows: list[dict[str, Any]], *, today: date) -> list[dict[str, Any]]:
    buckets = {bucket: {"bucket": bucket, "amount": 0.0, "count": 0} for bucket in AR_BUCKETS}
    saw_ar = False
    for row in rows:
        summary_values = _ar_summary_values(row)
        if summary_values:
            saw_ar = True
            for bucket, amount in summary_values.items():
                buckets[bucket]["amount"] += amount
                buckets[bucket]["count"] += 1 if amount else 0
            continue
        if not _is_ar_row(row):
            continue
        amount = _open_amount(row)
        if amount <= 0:
            continue
        saw_ar = True
        bucket = _ar_bucket(row, today=today)
        buckets[bucket]["amount"] += amount
        buckets[bucket]["count"] += 1
    return [
        {
            "bucket": bucket,
            "amount": round(values["amount"], 2) if saw_ar else None,
            "count": int(values["count"]),
        }
        for bucket, values in buckets.items()
    ]


def _ar_summary_values(row: dict[str, Any]) -> dict[str, float]:
    aliases = {
        "0-30": ("0-30", "0_30", "current", "1 - 30", "1-30"),
        "31-60": ("31-60", "31_60", "31 - 60"),
        "61-90": ("61-90", "61_90", "61 - 90"),
        "90+": ("90+", "90_plus", "91 and over", "91+", "over 90"),
    }
    values: dict[str, float] = {}
    for bucket, names in aliases.items():
        amount = _first_number(row, *names)
        if amount is not None:
            values[bucket] = amount
    return values


def _k1l_expense_rows(
    rows: list[dict[str, Any]],
    *,
    config: QboFinancialConfig,
    start: date | None,
    end: date | None,
) -> list[dict[str, Any]]:
    expenses: list[dict[str, Any]] = []
    for row in rows:
        if not _is_expense_row(row):
            continue
        if not _matches_any(_entity_haystack(row), config.k1l_entity_patterns):
            continue
        day = _coerce_date(row.get("transaction_date"))
        if day is None:
            continue
        if start and day < start:
            continue
        if end and day > end:
            continue
        bucket = _expense_bucket(row, config=config)
        if bucket is None:
            continue
        amount = _open_amount(row)
        if amount <= 0:
            continue
        expenses.append(
            {
                "Date": day.isoformat(),
                "Account": row.get("account_name") or row.get("category") or row.get("transaction_type") or "QBO Expense",
                "Amount": round(amount, 2),
                "Name": row.get("vendor_name") or row.get("entity_name"),
                "Class": row.get("class_name"),
                "Department": row.get("department_name"),
                "Location": row.get("location_name"),
                "Transaction Type": row.get("transaction_type"),
                "Transaction ID": row.get("transaction_id"),
                "qbo_expense_bucket": bucket,
                "source_authority": QBO_K1L_EXPENSE_AUTHORITY,
                "projection_mode": "read_only",
            }
        )
    return expenses


def _canonicalize_row(row: dict[str, Any]) -> dict[str, Any]:
    canonical: dict[str, Any] = {}
    for key, value in row.items():
        if key == "raw":
            continue
        normalized = _normalize_header(key)
        canonical_key = _FIELD_ALIASES.get(normalized, normalized)
        if canonical_key not in canonical or not canonical.get(canonical_key):
            canonical[canonical_key] = _clean_text(value)
    if row.get("qbo_row_kind") and not canonical.get("qbo_row_kind"):
        canonical["qbo_row_kind"] = row.get("qbo_row_kind")
    return canonical


def _is_ap_row(row: dict[str, Any]) -> bool:
    if row.get("qbo_row_kind") == "ap":
        return True
    text = " ".join(str(row.get(key) or "") for key in ("transaction_type", "account_name", "category")).casefold()
    return "bill" in text or "accounts payable" in text


def _is_ar_row(row: dict[str, Any]) -> bool:
    if row.get("qbo_row_kind") == "ar":
        return True
    text = " ".join(str(row.get(key) or "") for key in ("transaction_type", "account_name", "category")).casefold()
    return "invoice" in text or "accounts receivable" in text


def _is_expense_row(row: dict[str, Any]) -> bool:
    if row.get("qbo_row_kind") == "expense":
        return True
    if row.get("qbo_row_kind") in {"ap", "ar", "ap_summary", "ar_summary"}:
        return False
    text = " ".join(str(row.get(key) or "") for key in ("transaction_type", "account_name", "category")).casefold()
    if any(token in text for token in ("invoice", "bill", "accounts payable", "accounts receivable", "payment", "deposit", "revenue", "income")):
        return False
    if any(token in text for token in ("expense", "purchase", "check", "credit card", "repairs", "maintenance", "insurance")):
        return True
    return bool(row.get("transaction_date") and _open_amount(row) > 0 and (row.get("account_name") or row.get("category")))


def _expense_bucket(row: dict[str, Any], *, config: QboFinancialConfig) -> str | None:
    haystack = " ".join(
        str(row.get(key) or "")
        for key in (
            "account_name",
            "category",
            "vendor_name",
            "entity_name",
            "name",
            "memo",
            "description",
            "transaction_type",
        )
    ).casefold()
    if any(pattern.casefold() in haystack for pattern in config.excluded_expense_patterns):
        return None
    if any(pattern in haystack for pattern in _EMPLOYEE_PATTERNS):
        return "employee"
    if any(pattern in haystack for pattern in _RENTAL_TRUCK_TRAILER_PATTERNS):
        return "rental_trucks_trailers"
    if any(pattern in haystack for pattern in _MAINTENANCE_PATTERNS):
        return "maintenance"
    if any(pattern in haystack for pattern in _FUEL_PATTERNS):
        return "fuel"
    if any(pattern.casefold() in haystack for pattern in config.insurance_patterns):
        return "insurance"
    return None


def _ar_bucket(row: dict[str, Any], *, today: date) -> str:
    explicit = _clean_text(row.get("bucket") or row.get("aging_bucket"))
    if explicit:
        normalized = explicit.casefold().replace(" ", "")
        if "31" in normalized and "60" in normalized:
            return "31-60"
        if "61" in normalized and "90" in normalized:
            return "61-90"
        if "90" in normalized or "91" in normalized:
            return "90+"
        return "0-30"
    aging_days = _first_number(row, "aging_days", "age", "days_past_due")
    if aging_days is None:
        due_date = _coerce_date(row.get("due_date")) or _coerce_date(row.get("transaction_date"))
        aging_days = max((today - due_date).days, 0) if due_date else 0
    if aging_days <= 30:
        return "0-30"
    if aging_days <= 60:
        return "31-60"
    if aging_days <= 90:
        return "61-90"
    return "90+"


def _entity_haystack(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in (
            "class_name",
            "department_name",
            "location_name",
            "company_name",
            "entity_name",
            "customer_name",
            "memo",
            "description",
        )
    ).casefold()


def _matches_any(haystack: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern.casefold() in haystack for pattern in patterns if pattern)


def _open_amount(row: dict[str, Any]) -> float:
    amount = _first_number(row, "balance", "open_balance", "amount", "amount_usd", "total_amount", "total")
    return abs(amount or 0.0)


def _first_number(row: dict[str, Any], *names: str) -> float | None:
    for name in names:
        normalized = _normalize_header(name)
        for key, value in row.items():
            if _normalize_header(key) == normalized:
                parsed = _parse_number(value)
                if parsed is not None:
                    return parsed
    return None


def _first_int(row: dict[str, Any], *names: str) -> int:
    number = _first_number(row, *names)
    return int(number or 0)


def _number(value: Any) -> float:
    return _parse_number(value) or 0.0


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
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
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text.split()[0], fmt).date()
        except ValueError:
            continue
    return None


def _normalize_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    text = str(value).strip()
    return text or None


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default
