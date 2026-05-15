"""Read-only HR recruiting worklist analytics.

FleetPulse is the analytics layer only. Source records must come from the
approved TenStreet Outlook/Zapier workflow, not from TenStreet scraping or login
automation.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TABLE_ID = "01KR00WV4YHCB6BMYDE1EG7HEM"
DEFAULT_SLA_HOURS = (24, 48, 72)
SOURCE_AUTHORITY = "Zapier Table + approved TenStreet Outlook emails"
SOURCE_SYSTEM = "TenStreet Outlook/Zapier"
COMPLETED_STATUSES = {
    "complete",
    "completed",
    "closed",
    "done",
    "finished",
    "hired",
    "rejected",
    "declined",
    "withdrawn",
}

SOURCE_EMAIL_ALIASES = (
    "source_email_id",
    "sourceEmailId",
    "Source Email ID",
    "Outlook Message ID",
    "outlook_message_id",
    "internet_message_id",
    "message_id",
    "Message ID",
    "email_id",
)
APPLICANT_ALIASES = (
    "applicant",
    "Applicant",
    "applicant_id",
    "Applicant ID",
    "candidate",
    "Candidate",
    "driver",
    "Driver",
    "Name",
)
WORKLIST_ALIASES = (
    "worklist",
    "Worklist",
    "current_worklist",
    "Current Worklist",
    "Assigned Worklist",
    "queue",
    "Queue",
    "folder",
)
STATUS_ALIASES = (
    "status",
    "Status",
    "application_status",
    "Application Status",
    "lead_status",
    "Lead Status",
)
FIRST_ASSIGNED_ALIASES = (
    "first_assigned_at",
    "First Assigned At",
    "assigned_at",
    "Assigned At",
    "assignment_at",
    "Application Assignment Date",
    "receivedDateTime",
    "Received Date Time",
    "created_at",
    "Created At",
    "date",
    "Date",
)
WORKLIST_ENTERED_ALIASES = (
    "current_worklist_entered_at",
    "Current Worklist Entered At",
    "worklist_entered_at",
    "Worklist Entered At",
    "status_entered_at",
    "Status Entered At",
    "assigned_at",
    "Assigned At",
)
COMPLETED_AT_ALIASES = (
    "completed_at",
    "Completed At",
    "completion_date",
    "Completion Date",
    "closed_at",
    "Closed At",
    "hired_at",
    "Hired At",
    "finished_at",
    "Finished At",
)


@dataclass(frozen=True)
class HrRecruitingConfig:
    """Runtime configuration for the read-only HR recruiting projection."""

    table_id: str = DEFAULT_TABLE_ID
    source: str = "zapier_table"
    sla_hours: tuple[int, ...] = DEFAULT_SLA_HOURS
    snapshot_url: str = ""
    sharepoint_reporting_log_url: str = ""
    timeout_seconds: float = 20.0

    @classmethod
    def from_env(cls) -> "HrRecruitingConfig":
        return cls(
            table_id=os.getenv("ZAPIER_JOB_APPLICANTS_TABLE_ID", DEFAULT_TABLE_ID).strip()
            or DEFAULT_TABLE_ID,
            source=os.getenv("HR_RECRUITING_SOURCE", "zapier_table").strip() or "zapier_table",
            sla_hours=_sla_hours_from_env(),
            snapshot_url=os.getenv("HR_RECRUITING_SNAPSHOT_URL", "").strip(),
            sharepoint_reporting_log_url=os.getenv("SHAREPOINT_HR_REPORTING_LOG_URL", "").strip(),
            timeout_seconds=_float_env("HR_RECRUITING_TIMEOUT_SECONDS", 20.0),
        )

    @property
    def source_configured(self) -> bool:
        return bool(self.snapshot_url)

    def safe_status(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "table_id": self.table_id,
            "snapshot_configured": bool(self.snapshot_url),
            "sharepoint_reporting_log_configured": bool(self.sharepoint_reporting_log_url),
            "sla_hours": list(self.sla_hours),
            "source_authority": SOURCE_AUTHORITY,
            "projection_mode": "read_only",
            "pii_suppressed": True,
        }


@dataclass(frozen=True)
class RecruitingLead:
    dedupe_key: str
    worklist: str
    status: str
    first_assigned_at: datetime
    current_worklist_entered_at: datetime
    completed_at: datetime | None
    source_email_id_present: bool


@dataclass(frozen=True)
class SourceLoadResult:
    records: list[dict[str, Any]]
    status: str
    message: str | None = None


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _sla_hours_from_env() -> tuple[int, ...]:
    raw = os.getenv("HR_WORKLIST_SLA_HOURS", ",".join(str(value) for value in DEFAULT_SLA_HOURS))
    values: list[int] = []
    for part in raw.split(","):
        text = part.strip()
        if not text:
            continue
        try:
            value = int(text)
        except ValueError:
            continue
        if value > 0 and value not in values:
            values.append(value)
    return tuple(sorted(values)) or DEFAULT_SLA_HOURS


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_key(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def _find_value(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    normalized_aliases = {_normalize_key(alias) for alias in aliases}
    for key, value in row.items():
        if _normalize_key(str(key)) in normalized_aliases:
            return value
    return None


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _status_label(value: Any, completed_at: datetime | None) -> str:
    raw = _text(value)
    if not raw:
        return "Completed" if completed_at else "Active"
    return raw.replace("_", " ").replace("-", " ").strip().title()


def _status_key(status: str) -> str:
    return _normalize_key(status)


def _is_completed(lead: RecruitingLead) -> bool:
    return bool(lead.completed_at) or _status_key(lead.status) in COMPLETED_STATUSES


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return _datetime_from_number(float(value))

    raw = str(value).strip()
    if not raw:
        return None
    if raw.isdigit():
        return _datetime_from_number(float(raw))

    normalized = raw.replace("Z", "+00:00")
    try:
        return _ensure_aware(datetime.fromisoformat(normalized))
    except ValueError:
        pass

    for fmt in (
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%y %I:%M %p",
        "%m/%d/%Y %H:%M",
        "%m/%d/%y %H:%M",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _datetime_from_number(value: float) -> datetime | None:
    if value > 1_000_000_000_000:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    if value > 1_000_000_000:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if value > 20000:
        return datetime(1899, 12, 30, tzinfo=timezone.utc) + timedelta(days=value)
    return None


def _hours_between(start: datetime, end: datetime) -> float:
    return max((end - start).total_seconds() / 3600, 0.0)


def _round_hours(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def _hash_key(parts: tuple[str, ...]) -> str:
    body = "|".join(parts)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:32]


def _flatten_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    flattened: dict[str, Any] = {}
    for key, value in record.items():
        if key in {"fields", "values"} and isinstance(value, dict):
            flattened.update(value)
        elif key not in {"fields", "values"}:
            flattened[key] = value
    return flattened


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [_flatten_record(record) for record in payload if isinstance(record, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("records", "items", "rows", "data", "value"):
        records = payload.get(key)
        if isinstance(records, list):
            return [_flatten_record(record) for record in records if isinstance(record, dict)]
    if isinstance(payload.get("fields"), dict):
        return [_flatten_record(payload)]
    return []


def _normalize_lead(row: dict[str, Any]) -> tuple[RecruitingLead | None, str | None]:
    first_assigned_at = _parse_datetime(_find_value(row, FIRST_ASSIGNED_ALIASES))
    if first_assigned_at is None:
        return None, "missing_first_assigned_at"

    current_worklist_entered_at = (
        _parse_datetime(_find_value(row, WORKLIST_ENTERED_ALIASES)) or first_assigned_at
    )
    completed_at = _parse_datetime(_find_value(row, COMPLETED_AT_ALIASES))
    worklist = _text(_find_value(row, WORKLIST_ALIASES), "Unassigned")
    status = _status_label(_find_value(row, STATUS_ALIASES), completed_at)

    source_email_id = _text(_find_value(row, SOURCE_EMAIL_ALIASES))
    if source_email_id:
        dedupe_key = f"source-email:{_hash_key((source_email_id,))}"
        source_email_id_present = True
    else:
        applicant = _text(_find_value(row, APPLICANT_ALIASES), "unknown")
        dedupe_key = f"fallback:{_hash_key((applicant, worklist, first_assigned_at.isoformat()))}"
        source_email_id_present = False

    return (
        RecruitingLead(
            dedupe_key=dedupe_key,
            worklist=worklist,
            status=status,
            first_assigned_at=first_assigned_at,
            current_worklist_entered_at=current_worklist_entered_at,
            completed_at=completed_at,
            source_email_id_present=source_email_id_present,
        ),
        None,
    )


def _prefer_new_lead(existing: RecruitingLead, candidate: RecruitingLead) -> bool:
    if not existing.completed_at and candidate.completed_at:
        return True
    if existing.completed_at and not candidate.completed_at:
        return False
    return candidate.current_worklist_entered_at > existing.current_worklist_entered_at


async def _load_source_records(config: HrRecruitingConfig) -> SourceLoadResult:
    if not config.source_configured:
        return SourceLoadResult(
            records=[],
            status="snapshot_not_configured",
            message="Configure HR_RECRUITING_SNAPSHOT_URL with an approved Zapier/Outlook JSON snapshot.",
        )

    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            response = await client.get(config.snapshot_url)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "hr_recruiting_snapshot_http_error",
            extra={
                "hr_source": config.source,
                "hr_table_id": config.table_id,
                "status_code": exc.response.status_code,
            },
        )
        return SourceLoadResult(
            records=[],
            status="source_error",
            message=f"Snapshot endpoint returned HTTP {exc.response.status_code}.",
        )
    except Exception as exc:  # noqa: BLE001 - status payload should stay available.
        logger.warning(
            "hr_recruiting_snapshot_load_failed",
            extra={
                "hr_source": config.source,
                "hr_table_id": config.table_id,
                "error_type": type(exc).__name__,
            },
        )
        return SourceLoadResult(
            records=[],
            status="source_error",
            message=f"Snapshot load failed: {type(exc).__name__}.",
        )

    records = _extract_records(payload)
    logger.info(
        "hr_recruiting_snapshot_loaded",
        extra={
            "hr_source": config.source,
            "hr_table_id": config.table_id,
            "source_rows": len(records),
        },
    )
    return SourceLoadResult(
        records=records,
        status="ok" if records else "empty",
        message=None if records else "Snapshot was reachable but returned no applicant rows.",
    )


def build_hr_recruiting_dataset(
    records: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    config: HrRecruitingConfig | None = None,
    source_status: str = "ok",
    source_message: str | None = None,
) -> dict[str, Any]:
    """Build the dashboard/Power BI dataset without exposing applicant PII."""

    config = config or HrRecruitingConfig.from_env()
    as_of = _ensure_aware(now or _now_utc())
    today = as_of.date()
    visible_thresholds = tuple(sorted(set((*config.sla_hours, *DEFAULT_SLA_HOURS))))
    primary_stale_hours = min(config.sla_hours or DEFAULT_SLA_HOURS)

    deduped: dict[str, RecruitingLead] = {}
    invalid_rows = 0
    source_email_dedupe_rows = 0
    validation_errors: Counter[str] = Counter()
    for raw in records:
        lead, error = _normalize_lead(_flatten_record(raw))
        if error or lead is None:
            invalid_rows += 1
            validation_errors[error or "invalid_row"] += 1
            continue
        source_email_dedupe_rows += int(lead.source_email_id_present)
        existing = deduped.get(lead.dedupe_key)
        if existing is None or _prefer_new_lead(existing, lead):
            deduped[lead.dedupe_key] = lead

    leads = list(deduped.values())
    active_leads = [lead for lead in leads if not _is_completed(lead)]
    completed_leads = [lead for lead in leads if lead.completed_at is not None]

    summary = {
        "active_leads": len(active_leads),
        "new_leads_today": sum(1 for lead in leads if lead.first_assigned_at.date() == today),
        "avg_process_age_hours": _mean([_hours_between(lead.first_assigned_at, as_of) for lead in active_leads]),
        "stale_leads": sum(
            1
            for lead in active_leads
            if _hours_between(lead.current_worklist_entered_at, as_of) >= primary_stale_hours
        ),
        "completed_today": sum(1 for lead in completed_leads if lead.completed_at and lead.completed_at.date() == today),
    }

    by_worklist = _build_by_worklist(active_leads, leads, as_of, visible_thresholds)
    daily = _build_daily(leads, active_leads)
    status_counts = [
        {"status": status, "count": count}
        for status, count in sorted(Counter(lead.status for lead in leads).items(), key=lambda item: (-item[1], item[0]))
    ]
    trend = _build_trend(leads, active_leads, as_of, primary_stale_hours)
    derived_source_status = source_status if records or source_status != "ok" else "empty"

    dataset = {
        "generated_at": as_of.isoformat(),
        "projection_mode": "read_only",
        "source_system": SOURCE_SYSTEM,
        "source_authority": SOURCE_AUTHORITY,
        "source": config.source,
        "table_id": config.table_id,
        "source_status": derived_source_status,
        "source_message": source_message,
        "pii_suppressed": True,
        "sla_hours": list(config.sla_hours),
        "summary": summary,
        "by_worklist": by_worklist,
        "daily": daily,
        "status_counts": status_counts,
        "trend": trend,
        "row_counts": {
            "source_rows": len(records),
            "deduped_leads": len(leads),
            "active_leads": len(active_leads),
            "completed_leads": len(completed_leads),
            "invalid_rows": invalid_rows,
            "source_email_dedupe_rows": source_email_dedupe_rows,
        },
        "validation_errors": dict(validation_errors),
    }
    logger.info(
        "hr_recruiting_dataset_built",
        extra={
            "hr_source": config.source,
            "hr_table_id": config.table_id,
            "source_status": derived_source_status,
            "source_rows": len(records),
            "deduped_leads": len(leads),
            "invalid_rows": invalid_rows,
            "active_leads": len(active_leads),
        },
    )
    return dataset


def _build_by_worklist(
    active_leads: list[RecruitingLead],
    all_leads: list[RecruitingLead],
    as_of: datetime,
    thresholds: tuple[int, ...],
) -> list[dict[str, Any]]:
    new_today_by_worklist = Counter(
        lead.worklist for lead in all_leads if lead.first_assigned_at.date() == as_of.date()
    )
    grouped: dict[str, list[RecruitingLead]] = defaultdict(list)
    for lead in active_leads:
        grouped[lead.worklist].append(lead)

    rows: list[dict[str, Any]] = []
    for worklist, leads in grouped.items():
        worklist_ages = [_hours_between(lead.current_worklist_entered_at, as_of) for lead in leads]
        row: dict[str, Any] = {
            "worklist": worklist,
            "active_leads": len(leads),
            "new_leads_today": new_today_by_worklist.get(worklist, 0),
            "avg_age_hours": _mean(worklist_ages),
            "max_age_hours": _round_hours(max(worklist_ages)) if worklist_ages else 0.0,
        }
        for threshold in thresholds:
            row[f"stale_{threshold}h"] = sum(1 for age in worklist_ages if age >= threshold)
        rows.append(row)
    return sorted(rows, key=lambda row: (-int(row["active_leads"]), str(row["worklist"])))


def _build_daily(
    all_leads: list[RecruitingLead],
    active_leads: list[RecruitingLead],
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "new_leads": 0,
            "completed_leads": 0,
            "active_leads": 0,
            "process_times": [],
        }
    )
    active_keys = {lead.dedupe_key for lead in active_leads}
    for lead in all_leads:
        assigned_key = (lead.first_assigned_at.date().isoformat(), lead.worklist)
        buckets[assigned_key]["new_leads"] += 1
        if lead.dedupe_key in active_keys:
            buckets[assigned_key]["active_leads"] += 1
        if lead.completed_at is not None:
            completed_key = (lead.completed_at.date().isoformat(), lead.worklist)
            buckets[completed_key]["completed_leads"] += 1
            buckets[completed_key]["process_times"].append(_hours_between(lead.first_assigned_at, lead.completed_at))

    rows: list[dict[str, Any]] = []
    for (day, worklist), bucket in buckets.items():
        rows.append(
            {
                "date": day,
                "worklist": worklist,
                "new_leads": bucket["new_leads"],
                "completed_leads": bucket["completed_leads"],
                "active_leads": bucket["active_leads"],
                "avg_process_time_hours": _mean(bucket["process_times"]),
            }
        )
    return sorted(rows, key=lambda row: (str(row["date"]), str(row["worklist"])))


def _build_trend(
    all_leads: list[RecruitingLead],
    active_leads: list[RecruitingLead],
    as_of: datetime,
    primary_stale_hours: int,
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "new_leads": 0,
            "active_leads": 0,
            "stale_leads": 0,
            "ages": [],
        }
    )
    active_by_key = {lead.dedupe_key: lead for lead in active_leads}
    for lead in all_leads:
        day = lead.first_assigned_at.date().isoformat()
        buckets[day]["new_leads"] += 1
        active = active_by_key.get(lead.dedupe_key)
        if active is not None:
            buckets[day]["active_leads"] += 1
            buckets[day]["ages"].append(_hours_between(active.first_assigned_at, as_of))
            if _hours_between(active.current_worklist_entered_at, as_of) >= primary_stale_hours:
                buckets[day]["stale_leads"] += 1

    rows: list[dict[str, Any]] = []
    for day, bucket in buckets.items():
        rows.append(
            {
                "date": day,
                "active_leads": bucket["active_leads"],
                "new_leads": bucket["new_leads"],
                "stale_leads": bucket["stale_leads"],
                "avg_age_hours": _mean(bucket["ages"]),
            }
        )
    return sorted(rows, key=lambda row: str(row["date"]))


async def get_hr_recruiting_dataset(
    *,
    now: datetime | None = None,
    config: HrRecruitingConfig | None = None,
) -> dict[str, Any]:
    config = config or HrRecruitingConfig.from_env()
    source = await _load_source_records(config)
    return build_hr_recruiting_dataset(
        source.records,
        now=now,
        config=config,
        source_status=source.status,
        source_message=source.message,
    )
