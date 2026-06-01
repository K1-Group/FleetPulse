"""Read-only HR recruiting worklist analytics.

FleetPulse is the analytics layer only. Source records must come from the
approved Microsoft 365 Teams/SharePoint HR Driver Leads lane, not from Tenstreet
scraping, login automation, or API writeback.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import csv
import hashlib
import io
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

from services.hr_recruiting_workbook import (
    SOURCE_AUTHORITY as WORKBOOK_SOURCE_AUTHORITY,
    SOURCE_PROFILE as WORKBOOK_SOURCE_PROFILE,
    SOURCE_SYSTEM as WORKBOOK_SOURCE_SYSTEM,
    build_hr_recruiting_workbook_dataset,
)
from utils.dashboard_date_range import DashboardDateRange, dashboard_date_range, pct_change

logger = logging.getLogger(__name__)

DEFAULT_TABLE_ID = "01KR00WV4YHCB6BMYDE1EG7HEM"
DEFAULT_SLA_HOURS = (24, 48, 72)
DEFAULT_HR_TEAM_MEMBERS = ("Jordan",)
WORKBOOK_SOURCE = "hr_kpi_workbook"
LEGACY_SNAPSHOT_SOURCE = "zapier_table"
SOURCE_AUTHORITY = "Microsoft 365 Teams + SharePoint HR Driver Leads"
SOURCE_SYSTEM = "Microsoft 365 HR Driver Leads"
HARD_TARGETS: dict[str, dict[str, Any]] = {
    "new_hires_7d": {
        "label": "New Hires",
        "target": 5,
        "operator": ">=",
        "unit": "hires",
        "cadence": "7d",
        "display_target": ">= 5/week",
    },
    "active_qualified_pipeline": {
        "label": "Active Qualified Pipeline",
        "target": 10,
        "operator": ">=",
        "unit": "applicants",
        "cadence": "current",
        "display_target": ">= 10 applicants",
    },
    "first_touch_24h_pct": {
        "label": "First Touch Speed",
        "target": 0.95,
        "operator": ">=",
        "unit": "pct",
        "cadence": "current",
        "display_target": ">= 95% within 24h",
    },
    "stale_untouched_48h": {
        "label": "Stale Applicants",
        "target": 0,
        "operator": "<=",
        "unit": "applicants",
        "cadence": "current",
        "display_target": "0 untouched >48h",
    },
    "orientation_show_rate": {
        "label": "Orientation Show Rate",
        "target": 0.50,
        "operator": ">=",
        "unit": "pct",
        "cadence": "current",
        "display_target": ">= 50%",
    },
}
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
HIRED_STATUSES = {
    "hired",
    "hire",
    "newhire",
    "newhired",
    "driverhired",
    "onboarded",
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
FIRST_CONTACTED_AT_ALIASES = (
    "first_contacted_at",
    "First Contacted At",
    "first_contact_at",
    "First Contact At",
    "first_touch_at",
    "First Touch At",
    "contacted_at",
    "Contacted At",
    "called_at",
    "Called At",
)
HIRED_AT_ALIASES = (
    "hired_at",
    "Hired At",
    "hire_date",
    "Hire Date",
    "new_hire_at",
    "New Hire At",
    "driver_hired_at",
    "Driver Hired At",
)
QUALIFIED_ALIASES = (
    "qualified",
    "Qualified",
    "is_qualified",
    "Is Qualified",
    "qualified_pipeline",
    "Qualified Pipeline",
    "active_qualified_pipeline",
    "Active Qualified Pipeline",
    "driver_qualified",
    "Driver Qualified",
)
ORIENTATION_SCHEDULED_ALIASES = (
    "orientation_scheduled",
    "Orientation Scheduled",
    "orientation_scheduled_at",
    "Orientation Scheduled At",
    "orientation_date",
    "Orientation Date",
    "orientation_at",
    "Orientation At",
)
ORIENTATION_SHOWED_ALIASES = (
    "orientation_showed",
    "Orientation Showed",
    "orientation_attended",
    "Orientation Attended",
    "orientation_completed",
    "Orientation Completed",
    "showed_orientation",
    "Showed Orientation",
)
ORIENTATION_STATUS_ALIASES = (
    "orientation_status",
    "Orientation Status",
    "orientation_result",
    "Orientation Result",
)


@dataclass(frozen=True)
class HrRecruitingConfig:
    """Runtime configuration for the read-only HR recruiting projection."""

    table_id: str = DEFAULT_TABLE_ID
    source: str = WORKBOOK_SOURCE
    sla_hours: tuple[int, ...] = DEFAULT_SLA_HOURS
    snapshot_url: str = ""
    snapshot_path: str = ""
    workbook_path: str = ""
    conversion_workbook_path: str = ""
    sharepoint_reporting_log_url: str = ""
    timeout_seconds: float = 20.0
    team_members: tuple[str, ...] = DEFAULT_HR_TEAM_MEMBERS

    @classmethod
    def from_env(cls) -> "HrRecruitingConfig":
        snapshot_path = (
            os.getenv("HR_RECRUITING_STATE_PATH", "").strip()
            or os.getenv("HR_RECRUITING_SNAPSHOT_PATH", "").strip()
        )
        workbook_path = os.getenv("HR_RECRUITING_WORKBOOK_PATH", "").strip()
        conversion_workbook_path = os.getenv("HR_RECRUITING_CONVERSION_WORKBOOK_PATH", "").strip()
        return cls(
            table_id=os.getenv("ZAPIER_JOB_APPLICANTS_TABLE_ID", DEFAULT_TABLE_ID).strip()
            or DEFAULT_TABLE_ID,
            source=os.getenv("HR_RECRUITING_SOURCE", WORKBOOK_SOURCE).strip() or WORKBOOK_SOURCE,
            sla_hours=_sla_hours_from_env(),
            snapshot_url=os.getenv("HR_RECRUITING_SNAPSHOT_URL", "").strip(),
            snapshot_path=snapshot_path,
            workbook_path=workbook_path,
            conversion_workbook_path=conversion_workbook_path,
            sharepoint_reporting_log_url=os.getenv("SHAREPOINT_HR_REPORTING_LOG_URL", "").strip(),
            timeout_seconds=_float_env("HR_RECRUITING_TIMEOUT_SECONDS", 20.0),
            team_members=_csv_env("HR_RECRUITING_TEAM_MEMBERS", DEFAULT_HR_TEAM_MEMBERS),
        )

    @property
    def source_configured(self) -> bool:
        return bool(self.snapshot_url or self.snapshot_path or self.workbook_path)

    @property
    def workbook_source_path(self) -> str:
        if self.workbook_path:
            return self.workbook_path
        suffix = Path(self.snapshot_path).suffix.casefold() if self.snapshot_path else ""
        if suffix in {".xlsx", ".xlsm"}:
            return self.snapshot_path
        return ""

    @property
    def workbook_selected(self) -> bool:
        return bool(self.workbook_source_path) or self.source == WORKBOOK_SOURCE

    @property
    def source_selection_reason(self) -> str:
        if self.workbook_path:
            return (
                "HR_RECRUITING_WORKBOOK_PATH is configured; workbook mode is "
                "selected over legacy snapshot settings."
            )
        if self.workbook_source_path:
            return (
                "A workbook-compatible HR recruiting path is configured; "
                "workbook mode is selected over legacy snapshot settings."
            )
        if self.source == WORKBOOK_SOURCE:
            return (
                "HR_RECRUITING_SOURCE selects workbook mode; configure "
                "HR_RECRUITING_WORKBOOK_PATH with HR_Lead_KPI_Recheck_By_Phone.xlsx."
            )
        if self.source == LEGACY_SNAPSHOT_SOURCE:
            return (
                "Legacy snapshot fallback is selected because "
                "HR_RECRUITING_WORKBOOK_PATH is not configured."
            )
        return "Custom HR_RECRUITING_SOURCE is selected because workbook mode is not configured."

    def safe_status(self) -> dict[str, Any]:
        workbook_configured = bool(self.workbook_source_path)
        workbook_selected = self.workbook_selected
        source = WORKBOOK_SOURCE if workbook_selected else self.source
        return {
            "source": source,
            "selected_source": source,
            "configured_source": self.source,
            "preferred_source": WORKBOOK_SOURCE,
            "legacy_source": LEGACY_SNAPSHOT_SOURCE,
            "workbook_preferred": True,
            "source_selection_reason": self.source_selection_reason,
            "table_id": self.table_id,
            "snapshot_configured": bool(self.snapshot_url),
            "state_path_configured": bool(self.snapshot_path),
            "workbook_configured": workbook_configured,
            "workbook_path_env": "HR_RECRUITING_WORKBOOK_PATH",
            "conversion_workbook_configured": bool(self.conversion_workbook_path),
            "conversion_workbook_path_env": "HR_RECRUITING_CONVERSION_WORKBOOK_PATH",
            "legacy_snapshot_configured": bool(self.snapshot_url or self.snapshot_path),
            "sharepoint_reporting_log_configured": bool(self.sharepoint_reporting_log_url),
            "sla_hours": list(self.sla_hours),
            "hard_targets": _public_hard_targets(),
            "source_authority": WORKBOOK_SOURCE_AUTHORITY if workbook_selected else SOURCE_AUTHORITY,
            "source_system": WORKBOOK_SOURCE_SYSTEM if workbook_selected else SOURCE_SYSTEM,
            "source_profile": WORKBOOK_SOURCE_PROFILE if workbook_selected else "worklist_snapshot",
            "projection_mode": "read_only",
            "pii_suppressed": True,
            "team_members": list(self.team_members),
        }


@dataclass(frozen=True)
class RecruitingLead:
    dedupe_key: str
    worklist: str
    status: str
    first_assigned_at: datetime
    current_worklist_entered_at: datetime
    completed_at: datetime | None
    first_contacted_at: datetime | None
    hired_at: datetime | None
    qualified: bool
    qualification_evidence_present: bool
    orientation_scheduled: bool
    orientation_showed: bool
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


def _csv_env(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    return values or default


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


def _find_existing_value(row: dict[str, Any], aliases: tuple[str, ...]) -> tuple[bool, Any]:
    normalized_aliases = {_normalize_key(alias) for alias in aliases}
    for key, value in row.items():
        if _normalize_key(str(key)) in normalized_aliases:
            return True, value
    return False, None


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


def _is_hired(lead: RecruitingLead) -> bool:
    return bool(lead.hired_at) or _status_key(lead.status) in HIRED_STATUSES


def _matches_selected_or_day(
    value: datetime | None,
    selected_range: DashboardDateRange | None,
    fallback_day: date,
) -> bool:
    if not value:
        return False
    if selected_range:
        return selected_range.contains_datetime(value)
    return value.date() == fallback_day


def _lead_timestamps(lead: RecruitingLead) -> tuple[datetime | None, ...]:
    return (
        lead.first_assigned_at,
        lead.current_worklist_entered_at,
        lead.first_contacted_at,
        lead.completed_at,
        lead.hired_at,
    )


def _filter_leads_for_date_range(
    leads: list[RecruitingLead],
    selected_range: DashboardDateRange | None,
) -> list[RecruitingLead]:
    if not selected_range:
        return leads
    return [
        lead
        for lead in leads
        if any(selected_range.contains_datetime(value) for value in _lead_timestamps(lead))
    ]


def _period_metrics(
    leads: list[RecruitingLead],
    selected_range: DashboardDateRange | None,
) -> dict[str, int]:
    return {
        "new_leads": _new_leads_for_range(leads, selected_range),
        "new_applicants": len(leads),
        "interviews_scheduled": sum(1 for lead in leads if lead.orientation_scheduled),
        "new_hires": _new_hires_for_range(leads, selected_range),
        "follow_ups": _follow_ups_for_range(leads, selected_range),
    }


def _new_leads_for_range(
    leads: list[RecruitingLead],
    selected_range: DashboardDateRange | None,
) -> int:
    if not selected_range:
        return len(leads)
    return sum(1 for lead in leads if selected_range.contains_datetime(lead.first_assigned_at))


def _new_hires_for_range(
    leads: list[RecruitingLead],
    selected_range: DashboardDateRange | None,
) -> int:
    count = 0
    for lead in leads:
        hire_at = lead.hired_at or lead.completed_at
        if not _is_hired(lead) or not hire_at:
            continue
        if not selected_range or selected_range.contains_datetime(hire_at):
            count += 1
    return count


def _follow_ups_for_range(
    leads: list[RecruitingLead],
    selected_range: DashboardDateRange | None,
) -> int:
    return sum(
        1
        for lead in leads
        if lead.first_contacted_at
        and (not selected_range or selected_range.contains_datetime(lead.first_contacted_at))
    )


def _trend_comparison(
    all_leads: list[RecruitingLead],
    selected_range: DashboardDateRange | None,
) -> dict[str, Any] | None:
    if not selected_range:
        return None
    previous_range = selected_range.previous()
    current = _period_metrics(_filter_leads_for_date_range(all_leads, selected_range), selected_range)
    previous = _period_metrics(_filter_leads_for_date_range(all_leads, previous_range), previous_range)
    return {
        "current": current,
        "previous": previous,
        "lead_volume_change_pct": pct_change(current["new_leads"], previous["new_leads"]),
        "hire_volume_change_pct": pct_change(current["new_hires"], previous["new_hires"]),
        "follow_up_change_pct": pct_change(current["follow_ups"], previous["follow_ups"]),
    }


def _parse_boolish(value: Any, *, true_values: set[str] | None = None, false_values: set[str] | None = None) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = _normalize_key(str(value))
    if not normalized:
        return None
    truthy = {
        "1",
        "true",
        "yes",
        "y",
        "complete",
        "completed",
        "attended",
        "showed",
        "shown",
        "qualified",
        "eligible",
        "approved",
        "cleared",
        "ready",
        *(true_values or set()),
    }
    falsey = {
        "0",
        "false",
        "no",
        "n",
        "none",
        "na",
        "notqualified",
        "unqualified",
        "disqualified",
        "ineligible",
        "noshow",
        "missed",
        "cancelled",
        "canceled",
        *(false_values or set()),
    }
    if normalized in truthy:
        return True
    if normalized in falsey:
        return False
    return None


def _parse_qualification(row: dict[str, Any], *, status: str, worklist: str) -> tuple[bool, bool]:
    present, raw = _find_existing_value(row, QUALIFIED_ALIASES)
    parsed = _parse_boolish(raw) if present else None
    if parsed is not None:
        return True, parsed

    status_worklist_key = _normalize_key(f"{status} {worklist}")
    negative_terms = ("notqualified", "unqualified", "disqualified", "ineligible")
    positive_terms = ("qualified", "eligible", "approved", "cleared")
    if any(term in status_worklist_key for term in negative_terms):
        return True, False
    if any(term in status_worklist_key for term in positive_terms):
        return True, True
    return present, False


def _parse_orientation(row: dict[str, Any], *, status: str, worklist: str) -> tuple[bool, bool]:
    scheduled_present, scheduled_raw = _find_existing_value(row, ORIENTATION_SCHEDULED_ALIASES)
    showed_present, showed_raw = _find_existing_value(row, ORIENTATION_SHOWED_ALIASES)
    orientation_status_present, orientation_status_raw = _find_existing_value(row, ORIENTATION_STATUS_ALIASES)

    scheduled = False
    if scheduled_present:
        scheduled_bool = _parse_boolish(scheduled_raw)
        scheduled = scheduled_bool if scheduled_bool is not None else bool(_text(scheduled_raw))
    showed = False
    if showed_present:
        showed = bool(_parse_boolish(showed_raw))

    orientation_key = _normalize_key(str(orientation_status_raw or ""))
    if orientation_status_present and orientation_key:
        scheduled = True
        if any(term in orientation_key for term in ("noshow", "missed", "cancelled", "canceled")):
            showed = False
        elif any(term in orientation_key for term in ("showed", "shown", "attended", "complete", "completed")):
            showed = True

    status_worklist_key = _normalize_key(f"{status} {worklist}")
    if "orientation" in status_worklist_key:
        scheduled = True
        if any(term in status_worklist_key for term in ("noshow", "missed")):
            showed = False
        elif any(term in status_worklist_key for term in ("showed", "attended", "complete", "completed")):
            showed = True

    return scheduled, showed


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


def _extract_records_from_content(content: str, *, filename: str | None = None) -> list[dict[str, Any]]:
    stripped = content.lstrip("\ufeff").strip()
    if not stripped:
        return []
    suffix = Path(str(filename or "")).suffix.casefold()
    if suffix == ".json" or stripped[:1] in {"[", "{"}:
        return _extract_records(json.loads(stripped))
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


def _normalize_lead(row: dict[str, Any]) -> tuple[RecruitingLead | None, str | None]:
    first_assigned_at = _parse_datetime(_find_value(row, FIRST_ASSIGNED_ALIASES))
    if first_assigned_at is None:
        return None, "missing_first_assigned_at"

    current_worklist_entered_at = (
        _parse_datetime(_find_value(row, WORKLIST_ENTERED_ALIASES)) or first_assigned_at
    )
    first_contacted_at = _parse_datetime(_find_value(row, FIRST_CONTACTED_AT_ALIASES))
    hired_at = _parse_datetime(_find_value(row, HIRED_AT_ALIASES))
    completed_at = _parse_datetime(_find_value(row, COMPLETED_AT_ALIASES)) or hired_at
    worklist = _text(_find_value(row, WORKLIST_ALIASES), "Unassigned")
    status = _status_label(_find_value(row, STATUS_ALIASES), completed_at)
    qualification_evidence_present, qualified = _parse_qualification(row, status=status, worklist=worklist)
    orientation_scheduled, orientation_showed = _parse_orientation(row, status=status, worklist=worklist)

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
            first_contacted_at=first_contacted_at,
            hired_at=hired_at,
            qualified=qualified,
            qualification_evidence_present=qualification_evidence_present,
            orientation_scheduled=orientation_scheduled,
            orientation_showed=orientation_showed,
            source_email_id_present=source_email_id_present,
        ),
        None,
    )


def _prefer_new_lead(existing: RecruitingLead, candidate: RecruitingLead) -> bool:
    if not existing.completed_at and candidate.completed_at:
        return True
    if existing.completed_at and not candidate.completed_at:
        return False
    if not existing.hired_at and candidate.hired_at:
        return True
    if not existing.first_contacted_at and candidate.first_contacted_at:
        return True
    if not existing.orientation_showed and candidate.orientation_showed:
        return True
    if not existing.qualification_evidence_present and candidate.qualification_evidence_present:
        return True
    return candidate.current_worklist_entered_at > existing.current_worklist_entered_at


async def _load_source_records(config: HrRecruitingConfig) -> SourceLoadResult:
    if not config.source_configured:
        return SourceLoadResult(
            records=[],
            status="snapshot_not_configured",
            message="Configure HR_RECRUITING_WORKBOOK_PATH with HR_Lead_KPI_Recheck_By_Phone.xlsx. Legacy snapshot inputs require HR_RECRUITING_WORKBOOK_PATH unset and explicit HR_RECRUITING_SOURCE=zapier_table fallback.",
        )

    if config.snapshot_url:
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

    try:
        path = Path(config.snapshot_path)
        if not path.exists():
            return SourceLoadResult(
                records=[],
                status="snapshot_not_configured",
                message="HR recruiting state path is configured, but no snapshot has been imported yet.",
            )
        records = _extract_records_from_content(path.read_text(encoding="utf-8-sig"), filename=path.name)
    except Exception as exc:  # noqa: BLE001 - status payload should stay available.
        logger.warning(
            "hr_recruiting_state_load_failed",
            extra={
                "hr_source": config.source,
                "hr_table_id": config.table_id,
                "error_type": type(exc).__name__,
            },
        )
        return SourceLoadResult(
            records=[],
            status="source_error",
            message=f"Snapshot state load failed: {type(exc).__name__}.",
        )

    return SourceLoadResult(
        records=records,
        status="ok" if records else "empty",
        message=None if records else "Snapshot state file is present but contains no applicant rows.",
    )


def import_hr_recruiting_snapshot(
    content: str,
    *,
    filename: str | None = None,
    dry_run: bool = False,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Replace the legacy HR recruiting snapshot fallback as read-only evidence."""

    target_path = Path(path) if path else Path(
        os.getenv("HR_RECRUITING_STATE_PATH", "").strip()
        or os.getenv("HR_RECRUITING_SNAPSHOT_PATH", "").strip()
        or "/home/data/fleetpulse_hr_recruiting.json"
    )
    try:
        records = _extract_records_from_content(content, filename=filename)
    except Exception as exc:
        return {
            "status": "invalid",
            "source_authority": SOURCE_AUTHORITY,
            "projection_mode": "read_only",
            "dry_run": dry_run,
            "row_count": 0,
            "invalid_count": 1,
            "errors": [str(exc)],
            "state_path": str(target_path),
        }

    invalid_count = sum(
        1
        for row in records
        if _normalize_lead(_flatten_record(row))[0] is None
    )
    if not records:
        return {
            "status": "invalid",
            "source_authority": SOURCE_AUTHORITY,
            "projection_mode": "read_only",
            "dry_run": dry_run,
            "row_count": 0,
            "invalid_count": 1,
            "errors": ["hr_recruiting_snapshot_contains_no_rows"],
            "state_path": str(target_path),
        }

    payload = {
        "version": 1,
        "source_authority": SOURCE_AUTHORITY,
        "projection_mode": "read_only",
        "last_imported_at": _now_utc().isoformat(),
        "rows": records,
    }
    if not dry_run:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_suffix(f"{target_path.suffix}.tmp")
        tmp_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        tmp_path.replace(target_path)

    return {
        "status": "ok" if invalid_count < len(records) else "invalid",
        "source_authority": SOURCE_AUTHORITY,
        "projection_mode": "read_only",
        "dry_run": dry_run,
        "row_count": len(records),
        "invalid_count": invalid_count,
        "errors": [],
        "state_path": str(target_path),
    }


def validate_hr_recruiting_import_api_key(provided: str | None) -> None:
    expected = os.getenv("HR_RECRUITING_IMPORT_API_KEY", "").strip()
    if expected and provided != expected:
        raise PermissionError("Invalid HR recruiting import API key")


def _public_hard_targets() -> dict[str, dict[str, Any]]:
    return {
        key: {
            "label": spec["label"],
            "target": spec["target"],
            "operator": spec["operator"],
            "unit": spec["unit"],
            "cadence": spec["cadence"],
            "display_target": spec["display_target"],
        }
        for key, spec in HARD_TARGETS.items()
    }


def _target_met(actual: float, operator: str, target: float) -> bool:
    if operator == ">=":
        return actual >= target
    if operator == "<=":
        return actual <= target
    return actual == target


def _build_hard_target_results(
    actuals: dict[str, int | float | None],
    *,
    evidence_available: dict[str, bool],
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for key, spec in HARD_TARGETS.items():
        actual = actuals.get(key)
        can_evaluate = evidence_available.get(key, actual is not None) and actual is not None
        status = (
            "awaiting_feed"
            if not can_evaluate
            else "healthy" if _target_met(float(actual), str(spec["operator"]), float(spec["target"])) else "warning"
        )
        results[key] = {
            "key": key,
            "label": spec["label"],
            "actual": actual,
            "target": spec["target"],
            "operator": spec["operator"],
            "unit": spec["unit"],
            "cadence": spec["cadence"],
            "display_target": spec["display_target"],
            "status": status,
        }
    return results


def _empty_team_member(name: str, *, configured: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "configured": configured,
        "status": "configured",
        "evidence_sources": [],
        "lead_count": 0,
        "first_outreach_leads": 0,
        "real_discussion_leads": 0,
        "within_24h": 0,
        "recovered_24_48h": 0,
        "late_48_72h": 0,
        "failed_over_72h": 0,
        "total_outbound_attempts": 0,
        "within_24h_rate": None,
    }


def _build_team_members(
    configured_members: tuple[str, ...],
    *,
    first_outreach_rows: list[dict[str, Any]] | None = None,
    real_discussion_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    members: dict[str, dict[str, Any]] = {}
    display_order: list[str] = []

    def ensure_member(name: str, *, configured: bool = False) -> dict[str, Any]:
        display_name = _text(name)
        key = _normalize_key(display_name)
        if not key:
            key = f"member{len(members)}"
            display_name = "Unassigned"
        if key not in members:
            members[key] = _empty_team_member(display_name, configured=configured)
            display_order.append(key)
        elif configured:
            members[key]["configured"] = True
        return members[key]

    for member_name in configured_members:
        ensure_member(member_name, configured=True)

    def merge_evidence(rows: list[dict[str, Any]] | None, source: str) -> None:
        for row in rows or []:
            member = ensure_member(str(row.get("hr_member") or "Unassigned"))
            if source not in member["evidence_sources"]:
                member["evidence_sources"].append(source)
            leads = int(row.get("lead_count") or 0)
            if source == "first_outreach":
                member["first_outreach_leads"] += leads
            else:
                member["real_discussion_leads"] += leads
            member["within_24h"] += int(row.get("within_24h") or 0)
            member["recovered_24_48h"] += int(row.get("recovered_24_48h") or 0)
            member["late_48_72h"] += int(row.get("late_48_72h") or 0)
            member["failed_over_72h"] += int(row.get("failed_over_72h") or 0)
            member["total_outbound_attempts"] += int(row.get("total_outbound_attempts") or 0)

    merge_evidence(first_outreach_rows, "first_outreach")
    merge_evidence(real_discussion_rows, "real_discussion")

    rows: list[dict[str, Any]] = []
    for key in display_order:
        member = members[key]
        evidence_leads = member["first_outreach_leads"] + member["real_discussion_leads"]
        member["lead_count"] = max(member["first_outreach_leads"], member["real_discussion_leads"])
        member["status"] = "source_backed" if member["evidence_sources"] else "configured"
        member["within_24h_rate"] = round(member["within_24h"] / evidence_leads, 4) if evidence_leads else None
        rows.append(member)
    return rows


def _with_team_members(dataset: dict[str, Any], configured_members: tuple[str, ...]) -> dict[str, Any]:
    evidence = dataset.get("workbook_evidence") if isinstance(dataset.get("workbook_evidence"), dict) else {}
    dataset["team_members"] = _build_team_members(
        configured_members,
        first_outreach_rows=evidence.get("first_outreach_by_member") if isinstance(evidence, dict) else None,
        real_discussion_rows=evidence.get("real_discussion_by_member") if isinstance(evidence, dict) else None,
    )
    return dataset


def build_hr_recruiting_dataset(
    records: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    config: HrRecruitingConfig | None = None,
    source_status: str = "ok",
    source_message: str | None = None,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
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

    all_leads = list(deduped.values())
    selected_range = dashboard_date_range(start_date, end_date)
    leads = _filter_leads_for_date_range(all_leads, selected_range)
    active_leads = [lead for lead in leads if not _is_completed(lead)]
    completed_leads = [lead for lead in leads if lead.completed_at is not None]
    new_hire_start = today - timedelta(days=6)
    new_hires_7d = sum(
        1
        for lead in completed_leads
        if _is_hired(lead)
        and lead.completed_at
        and (
            selected_range.contains_datetime(lead.completed_at)
            if selected_range
            else new_hire_start <= lead.completed_at.date() <= today
        )
    )
    active_qualified_pipeline = sum(
        1 for lead in active_leads if lead.qualification_evidence_present and lead.qualified
    )
    first_touch_eligible = [
        lead
        for lead in leads
        if lead.first_contacted_at is not None or _hours_between(lead.first_assigned_at, as_of) >= 24
    ]
    first_touch_within_24h = sum(
        1
        for lead in first_touch_eligible
        if lead.first_contacted_at is not None
        and _hours_between(lead.first_assigned_at, lead.first_contacted_at) <= 24
    )
    first_touch_24h_pct = (
        round(first_touch_within_24h / len(first_touch_eligible), 4)
        if first_touch_eligible
        else None
    )
    stale_untouched_48h = sum(
        1
        for lead in active_leads
        if lead.first_contacted_at is None and _hours_between(lead.first_assigned_at, as_of) > 48
    )
    orientation_scheduled_count = sum(1 for lead in leads if lead.orientation_scheduled)
    orientation_show_count = sum(
        1 for lead in leads if lead.orientation_scheduled and lead.orientation_showed
    )
    orientation_show_rate = (
        round(orientation_show_count / orientation_scheduled_count, 4)
        if orientation_scheduled_count
        else None
    )

    summary = {
        "active_leads": len(active_leads),
        "new_leads_today": sum(
            1
            for lead in leads
            if _matches_selected_or_day(lead.first_assigned_at, selected_range, today)
        ),
        "avg_process_age_hours": _mean([_hours_between(lead.first_assigned_at, as_of) for lead in active_leads]),
        "stale_leads": sum(
            1
            for lead in active_leads
            if _hours_between(lead.current_worklist_entered_at, as_of) >= primary_stale_hours
        ),
        "completed_today": sum(
            1
            for lead in completed_leads
            if lead.completed_at
            and _matches_selected_or_day(lead.completed_at, selected_range, today)
        ),
        "new_hires_7d": new_hires_7d,
        "active_qualified_pipeline": active_qualified_pipeline,
        "first_touch_24h_pct": first_touch_24h_pct,
        "first_touch_eligible_count": len(first_touch_eligible),
        "first_touch_within_24h_count": first_touch_within_24h,
        "stale_untouched_48h": stale_untouched_48h,
        "orientation_scheduled_count": orientation_scheduled_count,
        "orientation_show_count": orientation_show_count,
        "orientation_show_rate": orientation_show_rate,
    }

    by_worklist = _build_by_worklist(active_leads, leads, as_of, visible_thresholds)
    daily = _build_daily(leads, active_leads)
    status_counts = [
        {"status": status, "count": count}
        for status, count in sorted(Counter(lead.status for lead in leads).items(), key=lambda item: (-item[1], item[0]))
    ]
    trend = _build_trend(leads, active_leads, as_of, primary_stale_hours)
    derived_source_status = source_status if records or source_status != "ok" else "empty"
    can_evaluate_targets = derived_source_status in {"ok", "empty"}
    hard_targets = _build_hard_target_results(
        {
            "new_hires_7d": new_hires_7d,
            "active_qualified_pipeline": active_qualified_pipeline,
            "first_touch_24h_pct": first_touch_24h_pct,
            "stale_untouched_48h": stale_untouched_48h,
            "orientation_show_rate": orientation_show_rate,
        },
        evidence_available={
            "new_hires_7d": can_evaluate_targets,
            "active_qualified_pipeline": can_evaluate_targets and (
                derived_source_status == "empty" or any(lead.qualification_evidence_present for lead in leads)
            ),
            "first_touch_24h_pct": can_evaluate_targets and len(first_touch_eligible) > 0,
            "stale_untouched_48h": can_evaluate_targets,
            "orientation_show_rate": can_evaluate_targets and orientation_scheduled_count > 0,
        },
    )
    hard_target_misses = [
        key for key, target in hard_targets.items() if target["status"] == "warning"
    ]
    hard_target_pending = [
        key for key, target in hard_targets.items() if target["status"] == "awaiting_feed"
    ]
    hard_target_status = (
        "awaiting_feed"
        if hard_target_pending and not hard_target_misses
        else "healthy" if not hard_target_misses and not hard_target_pending else "warning"
    )
    period_metrics = _period_metrics(leads, selected_range)
    trend_comparison = _trend_comparison(all_leads, selected_range)

    dataset = {
        "generated_at": as_of.isoformat(),
        "projection_mode": "read_only",
        "source_profile": "worklist_snapshot",
        "source_system": SOURCE_SYSTEM,
        "source_authority": SOURCE_AUTHORITY,
        "source": config.source,
        "table_id": config.table_id,
        "source_artifact": None,
        "source_status": derived_source_status,
        "source_message": source_message,
        "pii_suppressed": True,
        "sla_hours": list(config.sla_hours),
        "hard_targets": hard_targets,
        "hard_target_status": hard_target_status,
        "hard_target_misses": hard_target_misses,
        "hard_target_pending": hard_target_pending,
        "date_range": selected_range.as_dict() if selected_range else None,
        "period_metrics": period_metrics,
        "trend_comparison": trend_comparison,
        "summary": summary,
        "team_members": _build_team_members(config.team_members),
        "by_worklist": by_worklist,
        "daily": daily,
        "status_counts": status_counts,
        "trend": trend,
        "row_counts": {
            "source_rows": len(records),
            "deduped_leads": len(leads),
            "unfiltered_deduped_leads": len(all_leads),
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
    start_date: date | str | None = None,
    end_date: date | str | None = None,
) -> dict[str, Any]:
    config = config or HrRecruitingConfig.from_env()
    workbook_path = config.workbook_source_path
    if config.workbook_selected:
        return _with_team_members(
            build_hr_recruiting_workbook_dataset(
                workbook_path,
                now=now or _now_utc(),
                source=WORKBOOK_SOURCE,
                table_id=config.table_id,
                sla_hours=config.sla_hours,
                hard_targets=HARD_TARGETS,
                start_date=start_date,
                end_date=end_date,
                conversion_workbook_path=config.conversion_workbook_path,
            ),
            config.team_members,
        )
    source = await _load_source_records(config)
    return build_hr_recruiting_dataset(
        source.records,
        now=now,
        config=config,
        source_status=source.status,
        source_message=source.message,
        start_date=start_date,
        end_date=end_date,
    )
