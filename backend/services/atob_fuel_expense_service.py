"""AtoB manual fuel expense import service.

This module imports downloaded AtoB fuel reports as read-only expense
references for FleetPulse analytics. It does not write to AtoB, Geotab, or
Xcelerator, and it does not treat fuel card data as telemetry.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import csv
import io
import json
import logging
import os
from pathlib import Path
import re
import threading
from typing import Any

from utils.idempotency import stable_idempotency_key

logger = logging.getLogger(__name__)

ATOB_SOURCE_AUTHORITY = "AtoB manual fuel expense export"
ATOB_IDEMPOTENCY_NAMESPACE = "atob_fuel_expense_v1"
_STATE_LOCK = threading.Lock()

_FIELD_ALIASES = {
    "transactionid": "transaction_id",
    "transaction": "transaction_id",
    "txnid": "transaction_id",
    "authid": "transaction_id",
    "authorizationid": "transaction_id",
    "reference": "transaction_id",
    "referenceid": "transaction_id",
    "date": "transaction_date",
    "transactiondate": "transaction_date",
    "transactiondategmt": "transaction_date",
    "purchasedate": "transaction_date",
    "purchasedat": "transaction_date",
    "createdat": "transaction_date",
    "time": "transaction_date",
    "posteddate": "posted_date",
    "posteddategmt": "posted_date",
    "postdate": "posted_date",
    "settleddate": "posted_date",
    "merchant": "merchant_name",
    "merchantname": "merchant_name",
    "station": "merchant_name",
    "vendor": "merchant_name",
    "location": "merchant_name",
    "amount": "amount_usd",
    "total": "amount_usd",
    "totalamount": "amount_usd",
    "transactionamount": "amount_usd",
    "fuelcost": "amount_usd",
    "cost": "amount_usd",
    "netofdiscount": "net_amount_usd",
    "netamount": "net_amount_usd",
    "discount": "discount_usd",
    "status": "status",
    "merchantcategory": "merchant_category",
    "type": "fuel_type",
    "gallons": "gallons",
    "fuelgallons": "gallons",
    "volume": "gallons",
    "quantity": "gallons",
    "qty": "gallons",
    "pricepergallon": "price_per_gallon",
    "pricegal": "price_per_gallon",
    "pricepergal": "price_per_gallon",
    "ppg": "price_per_gallon",
    "unitprice": "price_per_gallon",
    "vehicle": "vehicle_name",
    "vehiclename": "vehicle_name",
    "asset": "vehicle_name",
    "assetname": "vehicle_name",
    "truck": "vehicle_name",
    "unit": "unit_number",
    "unitnumber": "unit_number",
    "equipment": "unit_number",
    "vehicleid": "vehicle_id",
    "assetid": "vehicle_id",
    "driver": "driver_name",
    "drivername": "driver_name",
    "cardholder": "driver_name",
    "employee": "driver_name",
    "card": "card_last4",
    "cardnumber": "card_last4",
    "cardlast4": "card_last4",
    "cardlastfour": "card_last4",
    "last4": "card_last4",
    "odometer": "odometer_miles",
    "odometermiles": "odometer_miles",
}


@dataclass(frozen=True)
class AtoBFuelExpenseRecord:
    id: str
    idempotency_key: str
    transaction_id: str | None
    transaction_date: str
    posted_date: str | None
    merchant_name: str | None
    amount_usd: float
    gallons: float | None
    price_per_gallon: float | None
    vehicle_name: str | None
    vehicle_id: str | None
    unit_number: str | None
    driver_name: str | None
    card_last4: str | None
    odometer_miles: float | None
    source_filename: str | None
    source_authority: str
    projection_mode: str
    created_at: str
    raw: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ParsedAtoBFuelExpense:
    row_number: int
    record: AtoBFuelExpenseRecord


@dataclass(frozen=True)
class AtoBFuelImportResult:
    status: str
    dry_run: bool
    total_records: int
    imported_count: int
    duplicate_count: int
    invalid_count: int
    errors: list[str]
    records: list[AtoBFuelExpenseRecord]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_authority": ATOB_SOURCE_AUTHORITY,
            "projection_mode": "read_only",
            "dry_run": self.dry_run,
            "total_records": self.total_records,
            "imported_count": self.imported_count,
            "duplicate_count": self.duplicate_count,
            "invalid_count": self.invalid_count,
            "errors": self.errors,
            "records": [record.as_dict() for record in self.records],
            "summary": summarize_records([record.as_dict() for record in self.records]),
        }


class AtoBFuelExpenseStateStore:
    def __init__(self, path: Path | str | None = None, retained_record_limit: int | None = None):
        self.path = Path(path) if path else _state_path_from_env()
        self.retained_record_limit = retained_record_limit or _retained_record_limit_from_env()

    def _empty_state(self) -> dict[str, Any]:
        return {
            "version": 1,
            "processed_idempotency_keys": [],
            "records": [],
            "last_imported_at": None,
        }

    def load_state(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty_state()
        with self.path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
        if not isinstance(state, dict):
            raise RuntimeError("atob_fuel_state_invalid")
        state.setdefault("processed_idempotency_keys", [])
        state.setdefault("records", [])
        state.setdefault("last_imported_at", None)
        return state

    def save_state(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, sort_keys=True, separators=(",", ":"))
        tmp_path.replace(self.path)

    def records(self) -> list[dict[str, Any]]:
        with _STATE_LOCK:
            state = self.load_state()
        records = [record for record in state.get("records", []) if isinstance(record, dict)]
        records.sort(key=lambda item: str(item.get("transaction_date") or ""), reverse=True)
        return records

    def append_records(
        self,
        parsed_records: list[ParsedAtoBFuelExpense],
        *,
        dry_run: bool = False,
    ) -> tuple[int, int, list[AtoBFuelExpenseRecord]]:
        with _STATE_LOCK:
            state = self.load_state()
            processed_keys = [
                str(key) for key in state.get("processed_idempotency_keys", [])
            ]
            processed = set(processed_keys)
            existing_records = [
                record
                for record in state.get("records", [])
                if isinstance(record, dict) and record.get("idempotency_key")
            ]
            imported = 0
            duplicates = 0
            accepted: list[AtoBFuelExpenseRecord] = []

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
                    existing_records.append(parsed.record.as_dict())

            if not dry_run:
                existing_records.sort(
                    key=lambda item: str(item.get("transaction_date") or ""),
                    reverse=True,
                )
                state["records"] = existing_records[: self.retained_record_limit]
                state["processed_idempotency_keys"] = processed_keys[
                    -self.retained_record_limit * 2 :
                ]
                state["last_imported_at"] = datetime.now(timezone.utc).isoformat()
                self.save_state(state)

            return imported, duplicates, accepted


def import_atob_fuel_expenses(
    content: str,
    *,
    filename: str | None = None,
    dry_run: bool = False,
    store: AtoBFuelExpenseStateStore | None = None,
) -> AtoBFuelImportResult:
    store = store or AtoBFuelExpenseStateStore()
    parsed_rows, errors = parse_atob_export_content(content, filename=filename)
    imported, duplicates, accepted = store.append_records(parsed_rows, dry_run=dry_run)
    invalid_count = len(errors)
    status = "ok" if imported or duplicates or not invalid_count else "invalid"

    logger.info(
        "atob_fuel_import_completed",
        extra={
            "dry_run": dry_run,
            "filename": filename,
            "imported_count": imported,
            "duplicate_count": duplicates,
            "invalid_count": invalid_count,
        },
    )

    return AtoBFuelImportResult(
        status=status,
        dry_run=dry_run,
        total_records=len(parsed_rows) + invalid_count,
        imported_count=imported,
        duplicate_count=duplicates,
        invalid_count=invalid_count,
        errors=errors,
        records=accepted,
    )


def parse_atob_export_content(
    content: str,
    *,
    filename: str | None = None,
) -> tuple[list[ParsedAtoBFuelExpense], list[str]]:
    rows = _load_export_rows(content, filename)
    parsed: list[ParsedAtoBFuelExpense] = []
    errors: list[str] = []
    created_at = datetime.now(timezone.utc).isoformat()

    for index, raw_row in enumerate(rows, start=1):
        try:
            record = _record_from_row(raw_row, index, filename, created_at)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        parsed.append(ParsedAtoBFuelExpense(row_number=index, record=record))

    return parsed, errors


def get_atob_fuel_summary(
    days: int = 30,
    *,
    store: AtoBFuelExpenseStateStore | None = None,
) -> dict[str, Any]:
    store = store or AtoBFuelExpenseStateStore()
    records = _filter_records_by_days(store.records(), days)
    summary = summarize_records(records)
    summary.update(
        {
            "source_authority": ATOB_SOURCE_AUTHORITY,
            "projection_mode": "read_only",
            "period_days": days,
        }
    )
    return summary


def get_atob_fuel_transactions(
    limit: int = 100,
    *,
    store: AtoBFuelExpenseStateStore | None = None,
) -> dict[str, Any]:
    store = store or AtoBFuelExpenseStateStore()
    safe_limit = min(max(int(limit or 100), 1), 500)
    return {
        "source_authority": ATOB_SOURCE_AUTHORITY,
        "projection_mode": "read_only",
        "records": store.records()[:safe_limit],
    }


def get_atob_daily_trends(
    days: int = 30,
    *,
    store: AtoBFuelExpenseStateStore | None = None,
) -> list[dict[str, Any]]:
    records = _filter_records_by_days((store or AtoBFuelExpenseStateStore()).records(), days)
    daily: dict[str, dict[str, Any]] = {}
    for record in records:
        if not _is_approved_fuel_record(record):
            continue
        day = _date_key(record.get("transaction_date"))
        if not day:
            continue
        bucket = daily.setdefault(
            day,
            {
                "date": day,
                "miles": 0,
                "gallons": 0.0,
                "cost": 0.0,
                "transaction_count": 0,
                "fuel_cost_source": "atob_manual_import",
            },
        )
        bucket["gallons"] += float(record.get("gallons") or 0)
        bucket["cost"] += float(record.get("amount_usd") or 0)
        bucket["transaction_count"] += 1

    return [
        {
            **bucket,
            "gallons": round(bucket["gallons"], 2),
            "cost": round(bucket["cost"], 2),
        }
        for _, bucket in sorted(daily.items())
    ]


def get_atob_vehicle_costs(
    days: int = 30,
    *,
    store: AtoBFuelExpenseStateStore | None = None,
) -> dict[str, dict[str, Any]]:
    records = _filter_records_by_days((store or AtoBFuelExpenseStateStore()).records(), days)
    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        if not _is_approved_fuel_record(record):
            continue
        label = _vehicle_label(record)
        if not label:
            continue
        key = _normalize_vehicle_key(label)
        bucket = grouped.setdefault(
            key,
            {
                "vehicle_name": label,
                "actual_cost": 0.0,
                "actual_gallons": 0.0,
                "transaction_count": 0,
            },
        )
        bucket["actual_cost"] += float(record.get("amount_usd") or 0)
        bucket["actual_gallons"] += float(record.get("gallons") or 0)
        bucket["transaction_count"] += 1

    return {
        key: {
            **bucket,
            "actual_cost": round(bucket["actual_cost"], 2),
            "actual_gallons": round(bucket["actual_gallons"], 2),
        }
        for key, bucket in grouped.items()
    }


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    records = [record for record in records if _is_approved_fuel_record(record)]
    total_cost = sum(float(record.get("amount_usd") or 0) for record in records)
    total_gallons = sum(float(record.get("gallons") or 0) for record in records)
    transaction_dates = [
        _date_key(record.get("transaction_date"))
        for record in records
        if _date_key(record.get("transaction_date"))
    ]
    vehicle_count = len({_normalize_vehicle_key(_vehicle_label(record)) for record in records if _vehicle_label(record)})
    avg_price = total_cost / total_gallons if total_gallons > 0 else None

    return {
        "transaction_count": len(records),
        "total_cost": round(total_cost, 2),
        "total_gallons": round(total_gallons, 2),
        "avg_price_per_gallon": round(avg_price, 3) if avg_price is not None else None,
        "vehicle_count": vehicle_count,
        "latest_transaction_date": max(transaction_dates) if transaction_dates else None,
    }


def _state_path_from_env() -> Path:
    configured = os.getenv("FLEETPULSE_ATOB_FUEL_STATE_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "data" / "atob_fuel_expenses.json"


def _retained_record_limit_from_env() -> int:
    try:
        return max(int(os.getenv("FLEETPULSE_ATOB_FUEL_RETAINED_RECORDS", "10000")), 1)
    except ValueError:
        return 10000


def _load_export_rows(content: str, filename: str | None) -> list[dict[str, Any]]:
    text = (content or "").lstrip("\ufeff").strip()
    if not text:
        return []

    suffix = Path(filename or "").suffix.lower()
    if suffix in {".json", ".jsonl"} or text[:1] in {"[", "{"}:
        return _load_json_rows(text)

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in sample else csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return [dict(row) for row in reader if any(str(value or "").strip() for value in row.values())]


def _load_json_rows(text: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        return rows

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("transactions", "records", "data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _record_from_row(
    raw_row: dict[str, Any],
    row_number: int,
    filename: str | None,
    created_at: str,
) -> AtoBFuelExpenseRecord:
    row = _canonicalize_row(raw_row)
    transaction_date = _parse_date_string(row.get("transaction_date"))
    if not transaction_date:
        raise ValueError(f"row {row_number}: missing transaction date")

    amount = _parse_number(row.get("net_amount_usd"))
    if amount is None:
        amount = _parse_number(row.get("amount_usd"))
    gallons = _parse_number(row.get("gallons"))
    price_per_gallon = _parse_number(row.get("price_per_gallon"))
    if amount is None and gallons is not None and price_per_gallon is not None:
        amount = gallons * price_per_gallon
    if price_per_gallon is None and amount is not None and gallons and gallons > 0:
        price_per_gallon = amount / gallons
    if gallons is None and amount is not None and price_per_gallon and price_per_gallon > 0:
        gallons = amount / price_per_gallon
    if amount is None:
        raise ValueError(f"row {row_number}: missing fuel amount")

    vehicle_name = _clean_text(row.get("vehicle_name"))
    unit_number = _clean_text(row.get("unit_number"))
    vehicle_id = _clean_text(row.get("vehicle_id"))
    vehicle_label = vehicle_name or unit_number or vehicle_id
    transaction_id = _clean_text(row.get("transaction_id"))
    merchant_name = _clean_text(row.get("merchant_name"))

    idempotency_key = stable_idempotency_key(
        ATOB_IDEMPOTENCY_NAMESPACE,
        transaction_id,
        transaction_date,
        round(amount, 2),
        round(gallons, 3) if gallons is not None else "",
        vehicle_label,
        merchant_name,
    )

    return AtoBFuelExpenseRecord(
        id=idempotency_key,
        idempotency_key=idempotency_key,
        transaction_id=transaction_id,
        transaction_date=transaction_date,
        posted_date=_parse_date_string(row.get("posted_date")),
        merchant_name=merchant_name,
        amount_usd=round(amount, 2),
        gallons=round(gallons, 3) if gallons is not None else None,
        price_per_gallon=round(price_per_gallon, 3) if price_per_gallon is not None else None,
        vehicle_name=vehicle_name or unit_number,
        vehicle_id=vehicle_id,
        unit_number=unit_number,
        driver_name=_clean_text(row.get("driver_name")),
        card_last4=_card_last4(row.get("card_last4")),
        odometer_miles=_parse_number(row.get("odometer_miles")),
        source_filename=filename,
        source_authority=ATOB_SOURCE_AUTHORITY,
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
    cleaned = text.replace("$", "").replace(",", "").replace("gal", "").replace("GAL", "")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    number = float(match.group(0))
    return -abs(number) if negative else number


def _parse_date_string(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date().isoformat() if value.tzinfo else value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    if not text:
        return None
    text = re.sub(r"\s+", " ", text.replace("Z", "+00:00"))
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.astimezone(timezone.utc).date().isoformat() if parsed.tzinfo else parsed.date().isoformat()
    except ValueError:
        pass
    for fmt in (
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%y %I:%M %p",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%y %H:%M",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _card_last4(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    return digits[-4:] if digits else text[-4:]


def _redact_raw_row(row: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in row.items():
        key_text = str(key)
        normalized = _normalize_header(key_text)
        if "card" in normalized and value is not None:
            last4 = _card_last4(value)
            redacted[key_text] = f"****{last4}" if last4 else "****"
        else:
            redacted[key_text] = value
    return redacted


def _filter_records_by_days(records: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    safe_days = min(max(int(days or 30), 1), 366)
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


def _raw_value(record: dict[str, Any], *names: str) -> Any:
    raw = record.get("raw")
    if not isinstance(raw, dict):
        return None
    normalized = {_normalize_header(name) for name in names}
    for key, value in raw.items():
        if _normalize_header(key) in normalized:
            return value
    return None


def _is_approved_fuel_record(record: dict[str, Any]) -> bool:
    status = str(_raw_value(record, "Status") or "").strip().casefold()
    if status and status != "approved":
        return False
    gallons = _parse_number(record.get("gallons") or _raw_value(record, "Gallons"))
    if gallons and gallons > 0:
        return True
    fuel_type = str(_raw_value(record, "Type") or "").casefold()
    return any(token in fuel_type for token in ("diesel", "fuel", "reefer", "unleaded"))


def _vehicle_label(record: dict[str, Any]) -> str | None:
    return _clean_text(
        record.get("vehicle_name") or record.get("unit_number") or record.get("vehicle_id")
    )


def _normalize_vehicle_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())
