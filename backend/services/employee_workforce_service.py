"""Employee Workforce projection backed by Time Doctor activity evidence."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import csv
import io
import json
import os
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

from configs.employee_workforce import EmployeeWorkforceConfig
from integrations.time_doctor.client import (
    TimeDoctorActivityFeedConfig,
    fetch_time_doctor_activity_rows,
)


SOURCE_AUTHORITY = "Time Doctor employee time and activity export"
PROJECTION_MODE = "read_only"


def get_employee_workforce_dataset(
    *,
    config: EmployeeWorkforceConfig | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    config = config or EmployeeWorkforceConfig.from_env()
    now = _ensure_aware(now or datetime.now(timezone.utc))
    rows, source_status = _load_activity_rows(config)
    return build_employee_workforce_dataset(rows, config=config, now=now, source_status=source_status)


def build_employee_workforce_dataset(
    rows: list[dict[str, Any]],
    *,
    config: EmployeeWorkforceConfig | None = None,
    now: datetime | None = None,
    source_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or EmployeeWorkforceConfig.from_env()
    now = _ensure_aware(now or datetime.now(timezone.utc))
    end_date = _date_in_timezone(now, config.timezone)
    start_date = end_date - timedelta(days=config.lookback_days - 1)
    normalized_rows = []
    invalid_rows = 0
    for row in rows:
        normalized = _normalize_activity_row(row, config)
        if not normalized:
            invalid_rows += 1
            continue
        if normalized["work_date"] < start_date or normalized["work_date"] > end_date:
            continue
        normalized_rows.append(normalized)

    employees = _employee_summaries(normalized_rows, end_date)
    summary = _summary(employees, normalized_rows, invalid_rows)
    status = source_status or _pending_source_status(config)
    validation = _validation(status, summary)
    return {
        "generated_at": now.isoformat(),
        "projection_mode": PROJECTION_MODE,
        "source_authority": SOURCE_AUTHORITY,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": config.lookback_days,
            "timezone": config.timezone,
        },
        "config": config.as_dict(),
        "summary": summary,
        "employees": employees,
        "source_status": status,
        "validation": validation,
    }


def _load_activity_rows(config: EmployeeWorkforceConfig) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if config.activity_feed_path:
        path = Path(config.activity_feed_path)
        if not path.exists():
            return [], {
                "status": "unavailable",
                "message": "Configured Time Doctor activity feed path does not exist.",
                "required_config": ["FLEETPULSE_TIMEDOCTOR_ACTIVITY_FEED_PATH"],
                "path": str(path),
            }
        try:
            rows = _load_rows_from_text(path.read_text(encoding="utf-8"), filename=path.name)
            return rows, {
                "status": "healthy",
                "message": "Loaded read-only Time Doctor activity feed from configured file.",
                "required_config": [],
                "path": str(path),
                "row_count": len(rows),
            }
        except Exception as exc:
            return [], {
                "status": "unavailable",
                "message": f"Time Doctor activity feed file could not be read: {type(exc).__name__}.",
                "required_config": ["FLEETPULSE_TIMEDOCTOR_ACTIVITY_FEED_PATH"],
                "path": str(path),
            }

    if config.activity_feed_url:
        try:
            rows = fetch_time_doctor_activity_rows(
                TimeDoctorActivityFeedConfig(
                    url=config.activity_feed_url,
                    api_token=os.getenv("FLEETPULSE_TIMEDOCTOR_API_TOKEN", "").strip(),
                    timeout_seconds=config.timeout_seconds,
                )
            )
            return rows, {
                "status": "healthy",
                "message": "Loaded read-only Time Doctor activity feed from configured URL.",
                "required_config": [],
                "row_count": len(rows),
            }
        except Exception as exc:
            return [], {
                "status": "unavailable",
                "message": f"Time Doctor activity feed URL is unavailable: {type(exc).__name__}.",
                "required_config": ["FLEETPULSE_TIMEDOCTOR_ACTIVITY_FEED_URL", "FLEETPULSE_TIMEDOCTOR_API_TOKEN"],
            }

    return [], _pending_source_status(config)


def _pending_source_status(config: EmployeeWorkforceConfig) -> dict[str, Any]:
    return {
        "status": "pending_config",
        "message": "No read-only Time Doctor activity feed is configured yet.",
        "required_config": [
            "FLEETPULSE_EMPLOYEE_WORKFORCE_SOURCE=time_doctor",
            "FLEETPULSE_TIMEDOCTOR_ACTIVITY_FEED_PATH or FLEETPULSE_TIMEDOCTOR_ACTIVITY_FEED_URL",
            "FLEETPULSE_TIMEDOCTOR_API_TOKEN for protected Time Doctor feeds",
        ],
        "company_id_configured": bool(config.company_id),
        "api_base_url_configured": bool(config.api_base_url),
        "api_token_configured": config.api_token_configured,
    }


def _normalize_activity_row(row: dict[str, Any], config: EmployeeWorkforceConfig) -> dict[str, Any] | None:
    employee_id = _first_text(row, "employee_id", "user_id", "userId", "id", "User ID")
    employee_name = _first_text(row, "employee_name", "user_name", "userName", "name", "User Name", "employee")
    email = _first_text(row, "email", "user_email", "employee_email")
    work_date = _first_date(
        row,
        config,
        "date",
        "work_date",
        "activity_date",
        "start_time",
        "start",
        "recorded_at",
        "created_at",
    )
    worked_minutes = _duration_minutes(
        _first_value(
            row,
            "worked_minutes",
            "duration_minutes",
            "time_worked_minutes",
            "tracked_minutes",
            "worked_seconds",
            "duration_seconds",
            "hours",
            "tracked_hours",
        )
    )
    if not (employee_id or employee_name or email) or not work_date:
        return None
    return {
        "employee_id": employee_id or email or employee_name,
        "employee_name": employee_name or email or employee_id or "Unassigned",
        "email": email or None,
        "department": _first_text(row, "department", "team", "group") or None,
        "project": _first_text(row, "project", "project_name", "task", "task_name") or None,
        "work_date": work_date,
        "worked_minutes": worked_minutes or 0.0,
        "productive_minutes": _duration_minutes(_first_value(row, "productive_minutes", "productive_seconds")),
        "idle_minutes": _duration_minutes(_first_value(row, "idle_minutes", "idle_seconds")),
        "manual_minutes": _duration_minutes(_first_value(row, "manual_minutes", "manual_time_minutes")),
        "source": "time_doctor",
    }


def _employee_summaries(rows: list[dict[str, Any]], end_date: date) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["employee_id"])].append(row)
    employees = []
    for employee_rows in grouped.values():
        worked = sum(float(row.get("worked_minutes") or 0) for row in employee_rows)
        productive_values = [float(row["productive_minutes"]) for row in employee_rows if row.get("productive_minutes") is not None]
        productive = sum(productive_values) if productive_values else None
        idle = sum(float(row.get("idle_minutes") or 0) for row in employee_rows)
        dates = {row["work_date"] for row in employee_rows}
        latest = max(dates) if dates else None
        employees.append(
            {
                "employee_id": employee_rows[0]["employee_id"],
                "employee_name": employee_rows[0]["employee_name"],
                "email": employee_rows[0]["email"],
                "department": employee_rows[0]["department"],
                "worked_hours": round(worked / 60, 2),
                "productive_hours": round(productive / 60, 2) if productive is not None else None,
                "idle_hours": round(idle / 60, 2),
                "productivity_pct": round((productive / worked) * 100, 1) if productive is not None and worked else None,
                "days_reported": len(dates),
                "active_today": latest == end_date,
                "latest_activity_date": latest.isoformat() if latest else None,
                "top_projects": _top_projects(employee_rows),
                "source": "time_doctor",
            }
        )
    employees.sort(key=lambda item: (-float(item["worked_hours"] or 0), item["employee_name"]))
    return employees[:100]


def _summary(employees: list[dict[str, Any]], rows: list[dict[str, Any]], invalid_rows: int) -> dict[str, Any]:
    worked = sum(float(employee["worked_hours"] or 0) for employee in employees)
    idle = sum(float(employee["idle_hours"] or 0) for employee in employees)
    productivity_values = [float(employee["productivity_pct"]) for employee in employees if employee.get("productivity_pct") is not None]
    return {
        "employees": len(employees),
        "active_today": sum(1 for employee in employees if employee.get("active_today")),
        "worked_hours": round(worked, 2),
        "idle_hours": round(idle, 2),
        "avg_productivity_pct": round(sum(productivity_values) / len(productivity_values), 1)
        if productivity_values
        else None,
        "activity_rows": len(rows),
        "invalid_rows": invalid_rows,
        "missing_timesheet_count": sum(1 for employee in employees if not employee.get("active_today")),
    }


def _validation(source_status: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    status = str(source_status.get("status") or "pending_config")
    if status == "healthy" and summary["activity_rows"]:
        return {
            "status": "verified",
            "state": "time_doctor_activity_loaded",
            "message": "Verified read-only Time Doctor employee activity rows.",
            "row_count": summary["activity_rows"],
        }
    if status == "healthy":
        return {
            "status": "pending_no_data",
            "state": "no_activity_rows",
            "message": "Time Doctor feed is configured but returned no activity rows for the selected window.",
            "row_count": 0,
        }
    return {
        "status": "pending",
        "state": "time_doctor_source_pending",
        "message": source_status.get("message") or "Time Doctor source is not configured.",
        "row_count": 0,
        "required_config": source_status.get("required_config", []),
    }


def _top_projects(rows: list[dict[str, Any]]) -> list[str]:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        project = row.get("project")
        if project:
            totals[str(project)] += float(row.get("worked_minutes") or 0)
    return [name for name, _ in sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:3]]


def _load_rows_from_text(content: str, *, filename: str = "") -> list[dict[str, Any]]:
    text = (content or "").lstrip("\ufeff").strip()
    if not text:
        return []
    suffix = Path(filename).suffix.casefold()
    if suffix in {".json", ".jsonl"} or text[:1] in {"[", "{"}:
        if suffix == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        payload = json.loads(text)
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            for key in ("rows", "items", "data", "activities", "worklogs", "users"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [row for row in value if isinstance(row, dict)]
            return [payload]
    return [dict(row) for row in csv.DictReader(io.StringIO(text))]


def _first_value(row: dict[str, Any], *aliases: str) -> Any:
    normalized = {_normalize_key(alias) for alias in aliases}
    for key, value in row.items():
        if _normalize_key(key) in normalized and value not in (None, ""):
            return value
    return None


def _first_text(row: dict[str, Any], *aliases: str) -> str:
    value = _first_value(row, *aliases)
    return str(value or "").strip()


def _first_date(row: dict[str, Any], config: EmployeeWorkforceConfig, *aliases: str) -> date | None:
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
    parsed = _parse_datetime(text, config)
    return _date_in_timezone(parsed, config.timezone) if parsed else None


def _duration_minutes(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().replace(",", "")
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return None
        number = float(match.group(0))
    if "second" in str(value).casefold() or abs(number) > 24 * 60:
        return max(number / 60, 0.0)
    if "hour" in str(value).casefold() or 0 < number <= 24:
        return max(number * 60, 0.0)
    return max(number, 0.0)


def _parse_datetime(value: Any, config: EmployeeWorkforceConfig) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value, config.timezone)
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _ensure_aware(parsed, config.timezone)


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
