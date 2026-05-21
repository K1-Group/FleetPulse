"""Fleet report delivery and schedule configuration helpers.

Email delivery is intentionally configuration-gated. FleetPulse can prepare and
route a report to a Power Automate/Zapier webhook, but it will not pretend a
report was sent when no delivery connector is configured.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

logger = logging.getLogger("fleetpulse.reports")

ALLOWED_PERIODS = {"daily", "weekly", "monthly"}
ALLOWED_FREQUENCIES = {"daily", "weekly", "monthly"}
EMAIL_WEBHOOK_ENV = "FLEETPULSE_REPORT_EMAIL_WEBHOOK_URL"
EMAIL_WEBHOOK_TOKEN_ENV = "FLEETPULSE_REPORT_EMAIL_WEBHOOK_TOKEN"
SCHEDULE_PATH_ENV = "FLEETPULSE_REPORT_SCHEDULE_PATH"
STATE_DIR_ENV = "FLEETPULSE_STATE_DIR"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _default_schedule() -> dict[str, Any]:
    return {
        "enabled": False,
        "period": "weekly",
        "frequency": "weekly",
        "recipients": [],
        "send_time": "07:00",
        "timezone": "America/Chicago",
        "weekday": 0,
        "day_of_month": 1,
    }


def _schedule_path() -> tuple[Path, bool]:
    explicit_path = os.getenv(SCHEDULE_PATH_ENV, "").strip()
    if explicit_path:
        return Path(explicit_path).expanduser(), True

    state_dir = os.getenv(STATE_DIR_ENV, "").strip()
    if state_dir:
        return Path(state_dir).expanduser() / "fleet_report_schedule.json", True

    return Path("/tmp/fleetpulse_report_schedule.json"), False


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"_load_error": f"{type(exc).__name__}: {exc}"}
    return payload if isinstance(payload, dict) else {"_load_error": "Schedule file is not a JSON object."}


def normalize_recipients(value: list[str] | str | None) -> list[str]:
    if value is None:
        raw_values: list[str] = []
    elif isinstance(value, str):
        raw_values = re.split(r"[,;\n]+", value)
    else:
        raw_values = value

    recipients: list[str] = []
    seen: set[str] = set()
    invalid: list[str] = []
    for item in raw_values:
        email = str(item).strip()
        if not email:
            continue
        key = email.lower()
        if not _EMAIL_RE.match(email):
            invalid.append(email)
            continue
        if key not in seen:
            seen.add(key)
            recipients.append(email)

    if invalid:
        raise ValueError(f"Invalid email recipient(s): {', '.join(invalid)}")
    return recipients


def _normalize_period(value: str) -> str:
    period = str(value or "weekly").strip().lower()
    if period not in ALLOWED_PERIODS:
        raise ValueError("Report period must be daily, weekly, or monthly.")
    return period


def _normalize_frequency(value: str) -> str:
    frequency = str(value or "weekly").strip().lower()
    if frequency not in ALLOWED_FREQUENCIES:
        raise ValueError("Schedule frequency must be daily, weekly, or monthly.")
    return frequency


def _normalize_send_time(value: str) -> str:
    send_time = str(value or "07:00").strip()
    if not re.match(r"^\d{2}:\d{2}$", send_time):
        raise ValueError("Schedule send_time must use HH:MM format.")
    hour, minute = (int(part) for part in send_time.split(":", 1))
    if hour > 23 or minute > 59:
        raise ValueError("Schedule send_time must be a valid 24-hour time.")
    return send_time


def _timezone(value: str) -> ZoneInfo:
    timezone_name = str(value or "America/Chicago").strip()
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unsupported timezone: {timezone_name}") from exc


def normalize_schedule(payload: dict[str, Any]) -> dict[str, Any]:
    schedule = {**_default_schedule(), **(payload or {})}
    schedule["enabled"] = bool(schedule.get("enabled"))
    schedule["period"] = _normalize_period(schedule.get("period", "weekly"))
    schedule["frequency"] = _normalize_frequency(schedule.get("frequency", "weekly"))
    schedule["recipients"] = normalize_recipients(schedule.get("recipients"))
    schedule["send_time"] = _normalize_send_time(schedule.get("send_time", "07:00"))

    timezone_name = str(schedule.get("timezone") or "America/Chicago").strip()
    _timezone(timezone_name)
    schedule["timezone"] = timezone_name

    weekday = schedule.get("weekday")
    schedule["weekday"] = 0 if weekday is None else max(0, min(6, int(weekday)))

    day_of_month = schedule.get("day_of_month")
    schedule["day_of_month"] = 1 if day_of_month is None else max(1, min(31, int(day_of_month)))

    if schedule["enabled"] and not schedule["recipients"]:
        raise ValueError("At least one email recipient is required for an enabled report schedule.")

    schedule["updated_at"] = datetime.now(timezone.utc).isoformat()
    return schedule


def _add_month(local_now: datetime) -> datetime:
    month = local_now.month + 1
    year = local_now.year
    if month > 12:
        month = 1
        year += 1
    return local_now.replace(year=year, month=month)


def calculate_next_run(schedule: dict[str, Any], now: datetime | None = None) -> str | None:
    if not schedule.get("enabled"):
        return None

    tz = _timezone(str(schedule.get("timezone") or "America/Chicago"))
    local_now = (now or datetime.now(timezone.utc)).astimezone(tz)
    hour, minute = (int(part) for part in str(schedule.get("send_time") or "07:00").split(":", 1))
    frequency = str(schedule.get("frequency") or "weekly")

    if frequency == "daily":
        candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local_now:
            candidate += timedelta(days=1)
        return candidate.isoformat()

    if frequency == "weekly":
        weekday = int(schedule.get("weekday", 0))
        days_ahead = (weekday - local_now.weekday()) % 7
        candidate = (local_now + timedelta(days=days_ahead)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if candidate <= local_now:
            candidate += timedelta(days=7)
        return candidate.isoformat()

    day = int(schedule.get("day_of_month", 1))
    year = local_now.year
    month = local_now.month
    last_day = calendar.monthrange(year, month)[1]
    candidate = local_now.replace(
        day=min(day, last_day), hour=hour, minute=minute, second=0, microsecond=0
    )
    if candidate <= local_now:
        next_month = _add_month(local_now)
        last_day = calendar.monthrange(next_month.year, next_month.month)[1]
        candidate = next_month.replace(
            day=min(day, last_day), hour=hour, minute=minute, second=0, microsecond=0
        )
    return candidate.isoformat()


def _delivery_configured() -> bool:
    return bool(os.getenv(EMAIL_WEBHOOK_ENV, "").strip())


def _delivery_idempotency_key(payload: dict[str, Any]) -> str:
    stable_payload = {
        "recipients": payload.get("recipients") or [],
        "period": payload.get("period") or "",
        "subject": payload.get("subject") or "",
        "generated_at": payload.get("generated_at") or "",
    }
    raw = json.dumps(stable_payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_report_schedule_status() -> dict[str, Any]:
    path, persistent_storage = _schedule_path()
    raw_schedule = _load_json(path)
    load_error = raw_schedule.pop("_load_error", None)
    try:
        schedule = normalize_schedule(raw_schedule)
    except ValueError:
        schedule = _default_schedule()

    return {
        "schedule": schedule,
        "next_run_at": calculate_next_run(schedule),
        "delivery_ready": _delivery_configured(),
        "required_config": [] if _delivery_configured() else [EMAIL_WEBHOOK_ENV],
        "persistent_storage": persistent_storage,
        "storage_ready": path.parent.exists() or persistent_storage,
        "load_error": load_error,
    }


def save_report_schedule(payload: dict[str, Any]) -> dict[str, Any]:
    schedule = normalize_schedule(payload)
    path, persistent_storage = _schedule_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(schedule, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)
    logger.info(
        "fleet_report_schedule_saved",
        extra={
            "enabled": schedule["enabled"],
            "frequency": schedule["frequency"],
            "period": schedule["period"],
            "recipient_count": len(schedule["recipients"]),
        },
    )

    return {
        "schedule": schedule,
        "next_run_at": calculate_next_run(schedule),
        "delivery_ready": _delivery_configured(),
        "required_config": [] if _delivery_configured() else [EMAIL_WEBHOOK_ENV],
        "persistent_storage": persistent_storage,
        "storage_ready": True,
    }


def send_report_email(payload: dict[str, Any]) -> dict[str, Any]:
    recipients = normalize_recipients(payload.get("recipients"))
    if not recipients:
        raise ValueError("At least one email recipient is required.")

    html = str(payload.get("html") or "").strip()
    if not html:
        raise ValueError("Report HTML is required.")

    period = _normalize_period(str(payload.get("period") or "weekly"))
    subject = str(payload.get("subject") or f"FleetPulse {period.capitalize()} Report").strip()
    message = str(payload.get("message") or "").strip()
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    generated_at = str(payload.get("generated_at") or datetime.now(timezone.utc).isoformat())

    webhook_url = os.getenv(EMAIL_WEBHOOK_ENV, "").strip()
    if not webhook_url:
        return {
            "status": "needs_configuration",
            "message": f"Set {EMAIL_WEBHOOK_ENV} to enable server-side report email delivery.",
            "delivery_ready": False,
            "required_config": [EMAIL_WEBHOOK_ENV],
        }

    headers = {
        "Accept": "application/json",
        "X-Idempotency-Key": _delivery_idempotency_key(
            {
                "recipients": recipients,
                "period": period,
                "subject": subject,
                "generated_at": generated_at,
            }
        ),
    }
    token = os.getenv(EMAIL_WEBHOOK_TOKEN_ENV, "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    delivery_payload = {
        "event_type": "fleetpulse.report.email_requested",
        "recipients": recipients,
        "subject": subject,
        "message": message,
        "period": period,
        "generated_at": generated_at,
        "summary": summary,
        "html": html,
    }

    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(webhook_url, json=delivery_payload, headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "fleet_report_email_webhook_failed",
            extra={"status_code": exc.response.status_code, "recipient_count": len(recipients)},
        )
        return {
            "status": "failed",
            "message": f"Report email webhook returned HTTP {exc.response.status_code}.",
            "delivery_ready": True,
        }
    except httpx.HTTPError as exc:
        logger.warning(
            "fleet_report_email_delivery_error",
            extra={"error_type": type(exc).__name__, "recipient_count": len(recipients)},
        )
        return {
            "status": "failed",
            "message": f"Report email delivery failed: {type(exc).__name__}.",
            "delivery_ready": True,
        }

    logger.info("fleet_report_email_submitted", extra={"recipient_count": len(recipients), "period": period})
    return {
        "status": "sent",
        "message": f"Report delivery accepted for {len(recipients)} recipient(s).",
        "delivery_ready": True,
    }
