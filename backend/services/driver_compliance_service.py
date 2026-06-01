"""Driver document compliance projection foundation.

This service is intentionally read-only. Until a source register is configured,
it returns a pending pipeline with the medical card, drug test, and MVR fields
FleetPulse will need to manage expiration risk.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
import csv
import io
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from configs.driver_compliance import DriverComplianceConfig


SOURCE_AUTHORITY = "Configured driver qualification document register"
PROJECTION_MODE = "read_only"
DOCUMENT_TYPES = [
    ("medical_card", "Medical Card"),
    ("drug_test", "Drug Test"),
    ("mvr", "MVR"),
]


def get_driver_compliance_dataset(
    *,
    config: DriverComplianceConfig | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    config = config or DriverComplianceConfig.from_env()
    now = _ensure_aware(now or datetime.now(timezone.utc), config.timezone)
    rows, source_status = _load_register_rows(config)
    return build_driver_compliance_dataset(rows, config=config, now=now, source_status=source_status)


def build_driver_compliance_dataset(
    rows: list[dict[str, Any]],
    *,
    config: DriverComplianceConfig | None = None,
    now: datetime | None = None,
    source_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or DriverComplianceConfig.from_env()
    now = _ensure_aware(now or datetime.now(timezone.utc), config.timezone)
    today = now.astimezone(_timezone(config.timezone)).date()
    drivers = []
    invalid_rows = 0
    for row in rows:
        driver = _normalize_driver(row, today=today, config=config)
        if not driver:
            invalid_rows += 1
            continue
        drivers.append(driver)
    drivers.sort(key=lambda item: (_driver_priority(item), item["driver_name"]))
    source = source_status or _pending_source_status(config)
    summary = _summary(drivers, invalid_rows)
    return {
        "generated_at": now.isoformat(),
        "projection_mode": PROJECTION_MODE,
        "source_authority": SOURCE_AUTHORITY,
        "config": config.as_dict(),
        "summary": summary,
        "document_types": [
            {"key": key, "label": label, "warning_days": config.warning_days}
            for key, label in DOCUMENT_TYPES
        ],
        "drivers": drivers[:250],
        "source_status": source,
        "validation": _validation(source, summary),
    }


def _load_register_rows(config: DriverComplianceConfig) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if config.source_path:
        path = Path(config.source_path)
        if not path.exists():
            return [], {
                "status": "unavailable",
                "message": "Configured driver compliance source path does not exist.",
                "required_config": ["FLEETPULSE_DRIVER_COMPLIANCE_SOURCE_PATH"],
                "path": str(path),
            }
        try:
            rows = _load_rows_from_text(path.read_text(encoding="utf-8"), filename=path.name)
            return rows, {
                "status": "healthy",
                "message": "Loaded read-only driver compliance register from configured file.",
                "required_config": [],
                "path": str(path),
                "row_count": len(rows),
            }
        except Exception as exc:
            return [], {
                "status": "unavailable",
                "message": f"Driver compliance register could not be read: {type(exc).__name__}.",
                "required_config": ["FLEETPULSE_DRIVER_COMPLIANCE_SOURCE_PATH"],
                "path": str(path),
            }
    if config.source_url:
        try:
            with httpx.Client(timeout=config.timeout_seconds) as client:
                response = client.get(config.source_url, headers={"Accept": "application/json"})
                response.raise_for_status()
                rows = _rows_from_payload(response.json())
            return rows, {
                "status": "healthy",
                "message": "Loaded read-only driver compliance register from configured URL.",
                "required_config": [],
                "row_count": len(rows),
            }
        except Exception as exc:
            return [], {
                "status": "unavailable",
                "message": f"Driver compliance source URL is unavailable: {type(exc).__name__}.",
                "required_config": ["FLEETPULSE_DRIVER_COMPLIANCE_SOURCE_URL"],
            }
    return [], _pending_source_status(config)


def _pending_source_status(config: DriverComplianceConfig) -> dict[str, Any]:
    return {
        "status": "pending_config",
        "message": "No driver qualification register source is configured yet.",
        "required_config": [
            "FLEETPULSE_DRIVER_COMPLIANCE_SOURCE_PATH or FLEETPULSE_DRIVER_COMPLIANCE_SOURCE_URL",
            "FLEETPULSE_DRIVER_COMPLIANCE_WARNING_DAYS",
        ],
        "document_fields": [key for key, _ in DOCUMENT_TYPES],
        "warning_days": config.warning_days,
    }


def _normalize_driver(
    row: dict[str, Any],
    *,
    today: date,
    config: DriverComplianceConfig,
) -> dict[str, Any] | None:
    driver_id = _first_text(row, "driver_id", "driverId", "driver_no", "DriverNo", "employee_id")
    driver_name = _first_text(row, "driver_name", "driverName", "Driver Name", "name", "driver")
    if not (driver_id or driver_name):
        return None
    documents = {
        "medical_card": _document_status(
            _first_date(row, config, "medical_card_expires", "medicalCardExpires", "medical_card_expiration", "medical_expiration", "dot_medical_card_expiration"),
            today,
            config.warning_days,
        ),
        "drug_test": _document_status(
            _first_date(row, config, "drug_test_expires", "drugTestExpires", "drug_test_expiration", "drug_test_due", "last_drug_test_expires"),
            today,
            config.warning_days,
        ),
        "mvr": _document_status(
            _first_date(row, config, "mvr_expires", "mvrExpires", "mvr_expiration", "mvr_due", "motor_vehicle_record_expiration"),
            today,
            config.warning_days,
        ),
    }
    statuses = [doc["status"] for doc in documents.values()]
    return {
        "driver_id": driver_id or driver_name,
        "driver_name": driver_name or driver_id,
        "email": _first_text(row, "email", "driver_email") or None,
        "phone": _first_text(row, "phone", "driver_phone") or None,
        "terminal": _first_text(row, "terminal", "location", "home_terminal") or None,
        "documents": documents,
        "overall_status": _overall_status(statuses),
        "next_expiration_date": _next_expiration(documents),
        "source": config.source,
    }


def _document_status(expires_on: date | None, today: date, warning_days: int) -> dict[str, Any]:
    if not expires_on:
        return {"expires_on": None, "days_remaining": None, "status": "missing"}
    days = (expires_on - today).days
    if days < 0:
        status = "expired"
    elif days <= warning_days:
        status = "warning"
    else:
        status = "valid"
    return {
        "expires_on": expires_on.isoformat(),
        "days_remaining": days,
        "status": status,
    }


def _overall_status(statuses: list[str]) -> str:
    if "expired" in statuses:
        return "expired"
    if "missing" in statuses:
        return "missing"
    if "warning" in statuses:
        return "warning"
    return "valid"


def _next_expiration(documents: dict[str, dict[str, Any]]) -> str | None:
    dates = [
        str(doc["expires_on"])
        for doc in documents.values()
        if doc.get("expires_on") and doc.get("status") != "expired"
    ]
    return min(dates) if dates else None


def _driver_priority(driver: dict[str, Any]) -> int:
    return {"expired": 0, "missing": 1, "warning": 2, "valid": 3}.get(driver["overall_status"], 9)


def _summary(drivers: list[dict[str, Any]], invalid_rows: int) -> dict[str, Any]:
    overall = Counter(driver["overall_status"] for driver in drivers)
    document_counts = {
        key: Counter(driver["documents"][key]["status"] for driver in drivers)
        for key, _ in DOCUMENT_TYPES
    }
    return {
        "drivers": len(drivers),
        "valid": overall.get("valid", 0),
        "warning": overall.get("warning", 0),
        "expired": overall.get("expired", 0),
        "missing": overall.get("missing", 0),
        "invalid_rows": invalid_rows,
        "medical_card_expiring": document_counts["medical_card"].get("warning", 0),
        "drug_test_expiring": document_counts["drug_test"].get("warning", 0),
        "mvr_expiring": document_counts["mvr"].get("warning", 0),
        "document_status_counts": {
            key: dict(counts)
            for key, counts in document_counts.items()
        },
    }


def _validation(source_status: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    status = str(source_status.get("status") or "pending_config")
    if status == "healthy" and summary["drivers"]:
        return {
            "status": "verified",
            "state": "driver_compliance_register_loaded",
            "message": "Verified read-only driver compliance expiration register.",
            "row_count": summary["drivers"],
        }
    if status == "healthy":
        return {
            "status": "pending_no_data",
            "state": "no_driver_compliance_rows",
            "message": "Driver compliance source is configured but returned no driver rows.",
            "row_count": 0,
        }
    return {
        "status": "pending",
        "state": "driver_compliance_source_pending",
        "message": source_status.get("message") or "Driver compliance source is not configured.",
        "row_count": 0,
        "required_config": source_status.get("required_config", []),
    }


def _load_rows_from_text(content: str, *, filename: str = "") -> list[dict[str, Any]]:
    text = (content or "").lstrip("\ufeff").strip()
    if not text:
        return []
    suffix = Path(filename).suffix.casefold()
    if suffix in {".json", ".jsonl"} or text[:1] in {"[", "{"}:
        if suffix == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        return _rows_from_payload(json.loads(text))
    return [dict(row) for row in csv.DictReader(io.StringIO(text))]


def _rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "drivers", "items", "value", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [payload]
    return []


def _first_value(row: dict[str, Any], *aliases: str) -> Any:
    normalized = {_normalize_key(alias) for alias in aliases}
    for key, value in row.items():
        if _normalize_key(key) in normalized and value not in (None, ""):
            return value
    return None


def _first_text(row: dict[str, Any], *aliases: str) -> str:
    value = _first_value(row, *aliases)
    return str(value or "").strip()


def _first_date(row: dict[str, Any], config: DriverComplianceConfig, *aliases: str) -> date | None:
    value = _first_value(row, *aliases)
    if isinstance(value, datetime):
        return _date_in_timezone(value, config.timezone)
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _date_in_timezone(value: datetime, timezone_name: str) -> date:
    return _ensure_aware(value, timezone_name).astimezone(_timezone(timezone_name)).date()


def _ensure_aware(value: datetime, timezone_name: str = "UTC") -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=_timezone(timezone_name)).astimezone(timezone.utc)
    return value.astimezone(timezone.utc)


def _timezone(timezone_name: str):
    try:
        return ZoneInfo(timezone_name or "UTC")
    except Exception:
        return timezone.utc


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())
