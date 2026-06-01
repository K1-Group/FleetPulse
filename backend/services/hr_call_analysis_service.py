"""Read-only HR call analysis and productivity analytics."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
import csv
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
from typing import Any

from configs.hr_call_analysis import DEFAULT_STATE_PATH, HrCallAnalysisConfig
from integrations.sharepoint.graph_drive_client import SharePointDriveClient, SharePointDriveFile
from utils.dashboard_date_range import DashboardDateRange, dashboard_date_range, pct_change

logger = logging.getLogger(__name__)

SOURCE_AUTHORITY = "Grasshopper call logs + SharePoint HR call-analysis reports"
DEPARTMENT_SOURCE_AUTHORITY = "Grasshopper call logs + SharePoint department call-analysis reports"
SOURCE_SYSTEM = "Grasshopper / Microsoft SharePoint"
PROJECTION_MODE = "read_only"

PHONE_PATTERN = re.compile(r"\(\d{3}\)\s*\d{3}-\d{4}|\b\d{3}[-.]\d{3}[-.]\d{4}\b")
ACTIVE_LEAD_STATUSES = {"new", "assigned", "active", "recruiterreview", "qualified"}
COMPLETED_LEAD_STATUSES = {"complete", "completed", "closed", "hired", "rejected", "declined", "withdrawn"}
DEPARTMENT_ALIASES = {
    "all": "All",
    "ops": "Operations",
    "operation": "Operations",
    "operations": "Operations",
    "dispatch": "Operations",
    "fleetops": "Operations",
    "fleetoperations": "Operations",
    "safety": "Fleet Safety",
    "fleetsafety": "Fleet Safety",
    "accounting": "Accounting",
    "qualitycontrol": "Quality Control",
    "sales": "Sales",
    "hr": "HR",
    "humanresources": "HR",
    "recruiting": "HR",
    "recruitment": "HR",
    "maintenance": "Maintenance",
    "shop": "Maintenance",
    "service": "Maintenance",
}


@dataclass(frozen=True)
class SourceLoadResult:
    call_rows: list[dict[str, Any]]
    analysis_reports: list[dict[str, Any]]
    lead_rows: list[dict[str, Any]]
    activity_rows: list[dict[str, Any]]
    status: str
    message: str | None = None
    last_imported_at: str | None = None


@dataclass(frozen=True)
class HrCallAnalysisFileSyncResult:
    analysis_file_key: str
    last_modified_at: str | None
    imported_count: int
    duplicate_count: int
    invalid_count: int
    errors: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "analysis_file_key": self.analysis_file_key,
            "last_modified_at": self.last_modified_at,
            "imported_count": self.imported_count,
            "duplicate_count": self.duplicate_count,
            "invalid_count": self.invalid_count,
            "errors": self.errors,
        }


@dataclass(frozen=True)
class HrCallAnalysisSyncResult:
    status: str
    dry_run: bool
    folder_path: str
    fetched_count: int
    imported_count: int
    duplicate_count: int
    invalid_count: int
    errors: list[str]
    files: list[HrCallAnalysisFileSyncResult]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_authority": SOURCE_AUTHORITY,
            "projection_mode": PROJECTION_MODE,
            "dry_run": self.dry_run,
            "folder_path": self.folder_path,
            "fetched_count": self.fetched_count,
            "imported_count": self.imported_count,
            "duplicate_count": self.duplicate_count,
            "invalid_count": self.invalid_count,
            "errors": self.errors,
            "files": [file.as_dict() for file in self.files],
        }


class HrCallAnalysisConfigError(RuntimeError):
    """Raised when SharePoint HR call sync is called without required config."""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        if value > 1_000_000_000_000:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        if value > 1_000_000_000:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if value > 20000:
            return datetime(1899, 12, 30, tzinfo=timezone.utc) + timedelta(days=value)
    raw = str(value).strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        return _ensure_aware(datetime.fromisoformat(normalized))
    except ValueError:
        pass
    for fmt in (
        "%m/%d/%Y %I:%M:%S %p",
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


def _date_str(value: datetime | None) -> str | None:
    return value.date().isoformat() if value else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _normalize_key(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def _normalize_department(value: Any, default: str = "HR") -> str:
    text = _text(value).replace("_", " ").replace("-", " ").strip()
    if not text:
        return default
    key = _normalize_key(text)
    if key in DEPARTMENT_ALIASES:
        return DEPARTMENT_ALIASES[key]
    if key.startswith("callanalysisreports"):
        tail = text.split("/")[-1].strip()
        return _normalize_department(tail, default=default)
    if key in {"k1", "k1group", "k1logistics"}:
        return default
    return " ".join(part[:1].upper() + part[1:].lower() for part in text.split())


def _department_key(value: Any) -> str:
    return _normalize_key(_normalize_department(value))


def _department_from_values(values: tuple[Any, ...], default: str = "HR") -> str:
    for value in values:
        text = _text(value)
        if not text:
            continue
        tokens = {_normalize_key(part) for part in re.split(r"[^A-Za-z0-9]+", text) if part}
        for token in tokens:
            if token in DEPARTMENT_ALIASES:
                return DEPARTMENT_ALIASES[token]
        parts = [part.strip() for part in re.split(r"[\\/]", text) if part.strip()]
        for part in reversed(parts):
            department = _normalize_department(part, default="")
            if department:
                return department
        if len(text) > 40:
            continue
        department = _normalize_department(text, default="")
        if department:
            return department
    return default


def _row_department(row: dict[str, Any], default: str = "HR") -> str:
    return _normalize_department(row.get("department") or row.get("source_department"), default=default)


def _department_matches(row: dict[str, Any], department: str) -> bool:
    normalized = _normalize_department(department, default="All")
    return normalized == "All" or _row_department(row) == normalized


def _first_datetime(row: dict[str, Any], fields: tuple[str, ...]) -> datetime | None:
    for field in fields:
        parsed = _parse_datetime(_find_value(row, (field,)))
        if parsed:
            return parsed
    return None


def _filter_rows_for_date_range(
    rows: list[dict[str, Any]],
    selected_range: DashboardDateRange | None,
    fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    if not selected_range:
        return rows
    return [
        row
        for row in rows
        if selected_range.contains_datetime(_first_datetime(row, fields))
    ]


def _filter_call_rows_for_active_extensions(
    rows: list[dict[str, Any]],
    active_extensions: set[str],
) -> list[dict[str, Any]]:
    if not active_extensions:
        return rows
    return [
        row
        for row in rows
        if _text(row.get("extension_id")) in active_extensions
    ]


def _filter_activity_rows_for_active_extensions(
    rows: list[dict[str, Any]],
    active_extensions: set[str],
) -> list[dict[str, Any]]:
    if not active_extensions:
        return rows
    return [
        row
        for row in rows
        if _text(row.get("extension_id")) in active_extensions
    ]


def _active_extensions_for_department(config: HrCallAnalysisConfig, department: str) -> set[str]:
    env_key = f"CALL_ANALYSIS_{_department_key(department).upper()}_ACTIVE_EXTENSIONS"
    configured = os.getenv(env_key, "").strip()
    if configured:
        return {part.strip() for part in configured.split(",") if part.strip()}
    if _normalize_department(department) == "HR":
        return set(config.active_extensions)
    return set()


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


def _hash_text(value: Any, config: HrCallAnalysisConfig) -> str | None:
    text = _text(value)
    if not text or text.casefold() == "unknown":
        return None
    digits = re.sub(r"\D+", "", text)
    body = digits or text.casefold()
    return hashlib.sha256(f"{config.hash_salt}:{body}".encode("utf-8")).hexdigest()[:32]


def _hash_key(parts: tuple[str, ...]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def _parse_duration_seconds(value: Any) -> int:
    if isinstance(value, (int, float)):
        return max(int(value), 0)
    text = _text(value).replace('="', "").replace('"', "").replace("=", "")
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    parts = [int(part) for part in text.split(":") if part != ""]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0


def _split_extension(value: Any) -> tuple[str, str]:
    text = _text(value, "Unknown")
    match = re.match(r"^(\d+)\s*-\s*(.+)$", text)
    if match:
        return match.group(1), match.group(2).strip()
    return text, text


def _parse_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = _normalize_key(str(value))
    if normalized in {"1", "true", "yes", "y", "resolved", "complete", "completed"}:
        return True
    if normalized in {"0", "false", "no", "n", "unresolved", "none", "na"}:
        return False
    return None


def _records_from_csv(content: str) -> list[dict[str, Any]]:
    lines = content.lstrip("\ufeff").splitlines()
    header_idx = 0
    for index, line in enumerate(lines):
        if line.startswith("Date/Time,") or line.startswith("Numbers and Extensions,"):
            header_idx = index
            break
    sample = "\n".join(lines[header_idx : header_idx + 5])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in sample else csv.excel
    return [
        dict(row)
        for row in csv.DictReader(io.StringIO("\n".join(lines[header_idx:])), dialect=dialect)
        if any(str(value or "").strip() for value in row.values())
    ]


def _parse_ratio_count(value: Any, position: int) -> int:
    parts = _text(value).split("/")
    if len(parts) <= position:
        return 0
    try:
        return int(re.sub(r"\D+", "", parts[position]) or 0)
    except ValueError:
        return 0


def _activity_report_date(content: str, filename: str | None) -> str | None:
    candidates = [filename or ""]
    for line in content.splitlines()[:5]:
        candidates.append(line)
    for candidate in candidates:
        match = re.search(r"Activity[_\s-]+(\d{1,2})[._-](\d{1,2})(?:[._-](\d{2,4}))?", candidate)
        if not match:
            continue
        month = int(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3) or _now_utc().year)
        if year < 100:
            year += 2000
        return date(year, month, day).isoformat()
    return None


def _department_from_extension_label(label: str, config: HrCallAnalysisConfig) -> str:
    extension_id, employee_name = _split_extension(label)
    normalized = _normalize_key(f"{extension_id} {employee_name}")
    if extension_id in set(config.active_extensions) or "hrmanager" in normalized:
        return "HR"
    if extension_id == "1" or "customeroperations" in normalized:
        return "Operations"
    if extension_id == "2" or "safety" in normalized:
        return "Fleet Safety"
    if extension_id == "3" or "accounting" in normalized:
        return "Accounting"
    if extension_id == "5" or "qualitycontrol" in normalized:
        return "Quality Control"
    if extension_id == "6" or "sales" in normalized:
        return "Sales"
    if extension_id == "0" or "otherquestions" in normalized:
        return "Other Questions"
    if extension_id.casefold() == "main":
        return "Main / Unrouted"
    if extension_id == "8" or "directory" in normalized:
        return "Name Directory"
    if extension_id.isdigit() and 700 <= int(extension_id) <= 799:
        return "Other 700-Series Extensions"
    return "Other / Unmapped"


def _activity_rows_from_csv(content: str, *, filename: str | None, config: HrCallAnalysisConfig) -> list[dict[str, Any]]:
    report_date = _activity_report_date(content, filename)
    rows = list(csv.reader(io.StringIO(content)))
    period = ""
    in_extensions = False
    activity_rows: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=1):
        if not row:
            continue
        label = _text(row[0])
        if re.fullmatch(r"[A-Za-z]+\s+\d{4}", label):
            period = label
            continue
        if label == "Extensions":
            in_extensions = True
            continue
        if not in_extensions or label in {"", "Totals"}:
            continue
        extension_id, employee_name = _split_extension(label)
        if not extension_id:
            continue
        department = _department_from_extension_label(label, config)
        calls = _parse_ratio_count(row[1] if len(row) > 1 else "", 1)
        activity_rows.append(
            {
                "activity_id": _hash_key((report_date or "", period, extension_id, label, str(row_number))),
                "department": department,
                "department_key": _department_key(department),
                "report_date": report_date,
                "activity_period": period,
                "extension_id": extension_id,
                "employee_name": employee_name,
                "activity_calls": calls,
                "activity_voicemails": _parse_ratio_count(row[1] if len(row) > 1 else "", 0),
                "activity_hangups": _parse_ratio_count(row[2] if len(row) > 2 else "", 0),
                "activity_faxes": _parse_ratio_count(row[3] if len(row) > 3 else "", 0),
                "activity_voice_calls": _parse_ratio_count(row[4] if len(row) > 4 else "", 0),
                "source_file": Path(filename or "").name,
            }
        )
    return activity_rows


def _extract_payload(
    content: str,
    *,
    filename: str | None = None,
    config: HrCallAnalysisConfig | None = None,
) -> dict[str, Any]:
    stripped = content.lstrip("\ufeff").strip()
    if not stripped:
        return {"call_rows": [], "analysis_reports": [], "lead_rows": [], "activity_rows": [], "department": ""}
    suffix = Path(filename or "").suffix.casefold()
    if (
        suffix == ".csv"
        and ("Report: Activity" in stripped or "Voice Mails / Calls / Ratio" in stripped)
    ):
        config = config or HrCallAnalysisConfig.from_env()
        return {
            "call_rows": [],
            "analysis_reports": [],
            "lead_rows": [],
            "activity_rows": _activity_rows_from_csv(stripped, filename=filename, config=config),
            "department": "",
        }
    if suffix == ".txt" and "CALL INTELLIGENCE REPORT" in stripped:
        return {"call_rows": [], "analysis_reports": [{"analysis_text": stripped, "filename": filename or ""}], "lead_rows": [], "activity_rows": [], "department": ""}
    if suffix == ".json" or stripped[:1] in {"[", "{"}:
        payload = json.loads(stripped)
        if isinstance(payload, list):
            return {"call_rows": payload, "analysis_reports": [], "lead_rows": [], "activity_rows": [], "department": ""}
        if not isinstance(payload, dict):
            return {"call_rows": [], "analysis_reports": [], "lead_rows": [], "activity_rows": [], "department": ""}
        return {
            "call_rows": list(payload.get("call_rows") or payload.get("calls") or payload.get("rows") or []),
            "analysis_reports": list(payload.get("analysis_reports") or payload.get("call_analysis_reports") or []),
            "lead_rows": list(payload.get("lead_rows") or payload.get("leads") or []),
            "activity_rows": list(payload.get("activity_rows") or payload.get("activity") or []),
            "department": _text(payload.get("department") or payload.get("source_department")),
        }
    return {"call_rows": _records_from_csv(stripped), "analysis_reports": [], "lead_rows": [], "activity_rows": [], "department": ""}


def _normalize_call_row(
    row: dict[str, Any],
    config: HrCallAnalysisConfig,
    *,
    row_number: int = 0,
    default_department: str = "HR",
) -> dict[str, Any] | None:
    started_at = _parse_datetime(
        _find_value(row, ("call_started_at", "call_start", "Date/Time", "date_time", "started_at"))
    )
    if not started_at:
        return None
    extension_id = _text(_find_value(row, ("extension_id", "Extension ID")))
    employee_name = _text(_find_value(row, ("employee_name", "employee", "agent_name", "Agent Name")))
    if not extension_id or not employee_name:
        extension_id, employee_name = _split_extension(_find_value(row, ("Extension", "extension")))
    direction = _text(_find_value(row, ("direction", "Direction")), "unknown").title()
    call_type = _text(_find_value(row, ("call_type", "Type", "type")), "Unknown")
    duration_seconds = _parse_duration_seconds(
        _find_value(row, ("duration_seconds", "duration", "Duration", "call_duration"))
    )
    caller_hash = _text(_find_value(row, ("caller_hash", "caller_phone_hash"))) or _hash_text(
        _find_value(row, ("Caller ID", "caller_id", "caller", "from")), config
    )
    connecting_hash = _text(_find_value(row, ("connecting_hash", "connecting_phone_hash"))) or _hash_text(
        _find_value(row, ("Connecting #", "connecting_number", "to")), config
    )
    external_hash = _text(_find_value(row, ("external_party_hash", "phone_hash", "candidate_phone_hash")))
    if not external_hash:
        external_hash = caller_hash or connecting_hash if direction.casefold() == "in" else connecting_hash or caller_hash
    vps_hash = _text(_find_value(row, ("vps_number_hash",))) or _hash_text(
        _find_value(row, ("VPS Number", "vps_number")), config
    )
    type_key = re.sub(r"[^a-z0-9]+", "_", call_type.casefold()).strip("_")
    source_row_number = int(_find_value(row, ("source_row_number",)) or row_number or 0)
    department_value = _find_value(row, ("department", "Department", "source_department", "team", "Team"))
    department = (
        _normalize_department(department_value, default=default_department)
        if _text(department_value)
        else _department_from_extension_label(f"{extension_id} - {employee_name}", config)
    )
    call_id = _text(_find_value(row, ("call_id", "id"))) or _hash_key(
        (
            department,
            _iso(started_at) or "",
            extension_id,
            employee_name,
            direction,
            call_type,
            str(duration_seconds),
            str(source_row_number),
        )
    )
    return {
        "call_id": call_id,
        "department": department,
        "department_key": _department_key(department),
        "call_started_at": _iso(started_at),
        "call_date": started_at.date().isoformat(),
        "month": started_at.strftime("%Y-%m"),
        "vps_number_hash": vps_hash,
        "external_party_hash": external_hash,
        "caller_hash": caller_hash,
        "connecting_hash": connecting_hash,
        "extension_id": extension_id,
        "employee_name": employee_name,
        "direction": direction,
        "call_type": call_type,
        "call_type_key": type_key,
        "duration_seconds": duration_seconds,
        "duration_minutes": round(duration_seconds / 60, 2),
        "is_voice_call": int("voice mail" not in type_key and "hangup" not in type_key),
        "is_connected": int("connected" in type_key and "not_connected" not in type_key),
        "is_not_connected": int("not_connected" in type_key),
        "is_voicemail": int("voice_mail" in type_key or "voicemail" in type_key),
        "is_hangup": int("hangup" in type_key),
        "is_outbound_attempt": int(direction.casefold() == "out"),
        "source_file": Path(str(_find_value(row, ("source_file",)) or "")).name,
        "source_row_number": source_row_number,
    }


def _regex_line(text: str, label: str) -> str:
    match = re.search(rf"^-\s*{re.escape(label)}:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _checked_category(text: str) -> str:
    for line in text.splitlines():
        if "[x]" in line.casefold():
            return line.split("]", 1)[-1].strip().strip("-").strip()
    return ""


def _section(text: str, start: str, end: str | None = None) -> str:
    start_index = text.find(start)
    if start_index < 0:
        return ""
    body = text[start_index + len(start) :]
    if end:
        end_index = body.find(end)
        if end_index >= 0:
            body = body[:end_index]
    return body.strip()


def _normalize_analysis_report(
    row: dict[str, Any],
    config: HrCallAnalysisConfig,
    *,
    default_department: str = "HR",
) -> dict[str, Any] | None:
    text = _text(row.get("analysis_text") or row.get("content") or row.get("text"))
    filename = _text(row.get("filename") or row.get("name") or row.get("source_file"))
    if not text and not filename:
        return None
    department = _department_from_values(
        (
            row.get("department"),
            row.get("source_department"),
            row.get("source_folder"),
            row.get("folder_path"),
            "HR" if "HR Manager" in filename else "",
        ),
        default=default_department,
    )
    file_key = _text(row.get("analysis_file_key")) or _hash_key(
        (department, filename, _text(row.get("created_at")), _text(row.get("updated_at")))
    )
    call_dt = _parse_datetime(_regex_line(text, "Date & Time") or row.get("call_started_at") or row.get("created_at"))
    sentiment = _regex_line(text, "Overall Sentiment") or _text(row.get("sentiment"))
    resolved = _parse_bool(_regex_line(text, "Was the issue resolved?") or row.get("resolved"))
    urgent = _parse_bool(_regex_line(text, "Urgent") or row.get("urgent"))
    errors_section = _section(text, "HUMAN ERRORS DETECTED", "CUSTOMER SENTIMENT ANALYSIS")
    no_errors = "no errors detected" in errors_section.casefold()
    action_items = len(re.findall(r"^\[\s*\]", text, flags=re.MULTILINE))
    return {
        "analysis_file_key": file_key,
        "department": department,
        "department_key": _department_key(department),
        "caller_phone_hash": _text(row.get("caller_phone_hash")) or _hash_text(filename, config),
        "call_date": _date_str(call_dt),
        "call_started_at": _iso(call_dt),
        "agent_name": _regex_line(text, "Agent Name") or _text(row.get("agent_name"), "Unknown"),
        "extension_label": _text(row.get("extension_label"), "HR Manager" if "HR Manager" in filename else "Unknown"),
        "category": _checked_category(text) or _text(row.get("category"), "Unclassified"),
        "sentiment": sentiment or "Unknown",
        "resolved": resolved,
        "resolution_quality": _regex_line(text, "Resolution Quality") or _text(row.get("resolution_quality")),
        "human_errors_detected": bool(errors_section and not no_errors),
        "urgent": bool(urgent),
        "action_items_count": action_items,
        "language": _regex_line(text, "Language") or _text(row.get("language")),
        "created_at": _text(row.get("created_at")),
        "updated_at": _text(row.get("updated_at")),
        "size_bytes": int(row.get("size_bytes") or 0),
        "source_folder": _text(row.get("source_folder"), "SharePoint HR Call Analysis"),
    }


def _normalize_lead_row(
    row: dict[str, Any],
    config: HrCallAnalysisConfig,
    *,
    default_department: str = "HR",
) -> dict[str, Any] | None:
    assigned_at = _parse_datetime(_find_value(row, ("first_assigned_at", "assigned_at", "receivedDateTime", "date")))
    if not assigned_at:
        return None
    phone_hash = _text(_find_value(row, ("phone_hash", "candidate_phone_hash", "external_party_hash")))
    if not phone_hash:
        phone_hash = _hash_text(_find_value(row, ("phone", "Phone", "mobile", "Mobile", "caller_id")), config)
    if not phone_hash:
        return None
    status = _text(_find_value(row, ("status", "application_status", "lead_status")), "Active")
    completed_at = _parse_datetime(_find_value(row, ("completed_at", "hired_at", "closed_at")))
    lead_key = _text(_find_value(row, ("lead_key", "source_email_id", "message_id", "applicant_id"))) or _hash_key(
        (phone_hash, assigned_at.isoformat())
    )
    department = _normalize_department(
        _find_value(row, ("department", "Department", "source_department", "team", "Team")),
        default=default_department,
    )
    return {
        "lead_key": _hash_key((lead_key,)),
        "department": department,
        "department_key": _department_key(department),
        "phone_hash": phone_hash,
        "worklist": _text(_find_value(row, ("worklist", "queue", "Current Worklist")), "Unassigned"),
        "status": status,
        "first_assigned_at": _iso(assigned_at),
        "completed_at": _iso(completed_at),
    }


def _normalize_activity_row(
    row: dict[str, Any],
    config: HrCallAnalysisConfig,
    *,
    row_number: int = 0,
    default_department: str = "HR",
) -> dict[str, Any] | None:
    extension_label = _text(_find_value(row, ("extension", "Extension", "Numbers and Extensions")))
    extension_id = _text(_find_value(row, ("extension_id", "Extension ID")))
    employee_name = _text(_find_value(row, ("employee_name", "employee", "Agent Name")))
    if not extension_id or not employee_name:
        extension_id, employee_name = _split_extension(extension_label or extension_id)
    if not extension_id:
        return None
    report_dt = _parse_datetime(_find_value(row, ("report_date", "activity_date", "date")))
    report_date = _date_str(report_dt) or _text(row.get("report_date"))
    department = _normalize_department(
        row.get("department") or row.get("source_department") or _department_from_extension_label(
            f"{extension_id} - {employee_name}",
            config,
        ),
        default=default_department,
    )
    activity_id = _text(row.get("activity_id")) or _hash_key(
        (
            report_date,
            _text(row.get("activity_period")),
            extension_id,
            employee_name,
            str(row_number),
        )
    )
    return {
        "activity_id": activity_id,
        "department": department,
        "department_key": _department_key(department),
        "report_date": report_date,
        "activity_period": _text(row.get("activity_period")),
        "extension_id": extension_id,
        "employee_name": employee_name,
        "activity_calls": int(row.get("activity_calls") or row.get("calls") or 0),
        "activity_voicemails": int(row.get("activity_voicemails") or row.get("voicemails") or 0),
        "activity_hangups": int(row.get("activity_hangups") or row.get("hangups") or 0),
        "activity_faxes": int(row.get("activity_faxes") or row.get("faxes") or 0),
        "activity_voice_calls": int(row.get("activity_voice_calls") or row.get("voice_calls") or 0),
        "source_file": Path(str(row.get("source_file") or "")).name,
    }


def _dedupe(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = _text(row.get(key))
        if value:
            deduped[value] = row
    return list(deduped.values())


def _read_state(path: Path) -> SourceLoadResult:
    if not path.exists():
        return SourceLoadResult(
            call_rows=[],
            analysis_reports=[],
            lead_rows=[],
            activity_rows=[],
            status="snapshot_not_configured",
            message="Import HR call analysis evidence or configure SharePoint sync.",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return SourceLoadResult(
            call_rows=[],
            analysis_reports=[],
            lead_rows=[],
            activity_rows=[],
            status="source_error",
            message=f"HR call analysis state load failed: {type(exc).__name__}.",
        )
    has_evidence = bool(payload.get("call_rows") or payload.get("analysis_reports") or payload.get("activity_rows"))
    return SourceLoadResult(
        call_rows=list(payload.get("call_rows") or []),
        analysis_reports=list(payload.get("analysis_reports") or []),
        lead_rows=list(payload.get("lead_rows") or []),
        activity_rows=list(payload.get("activity_rows") or []),
        status="ok" if has_evidence else "empty",
        message=None if has_evidence else "State file is present but contains no call evidence.",
        last_imported_at=payload.get("last_imported_at"),
    )


def _write_state(
    path: Path,
    *,
    call_rows: list[dict[str, Any]],
    analysis_reports: list[dict[str, Any]],
    lead_rows: list[dict[str, Any]],
    activity_rows: list[dict[str, Any]],
) -> None:
    payload = {
        "version": 1,
        "source_authority": SOURCE_AUTHORITY,
        "projection_mode": PROJECTION_MODE,
        "last_imported_at": _now_utc().isoformat(),
        "call_rows": call_rows,
        "analysis_reports": analysis_reports,
        "lead_rows": lead_rows,
        "activity_rows": activity_rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    tmp_path.replace(path)


def import_hr_call_analysis_snapshot(
    content: str,
    *,
    filename: str | None = None,
    department: str | None = None,
    dry_run: bool = False,
    path: str | Path | None = None,
    config: HrCallAnalysisConfig | None = None,
) -> dict[str, Any]:
    """Merge HR call analysis evidence into the read-only state file."""

    config = config or HrCallAnalysisConfig.from_env()
    target_path = Path(path or config.state_path or DEFAULT_STATE_PATH)
    try:
        payload = _extract_payload(content, filename=filename, config=config)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "invalid",
            "source_authority": SOURCE_AUTHORITY,
            "projection_mode": PROJECTION_MODE,
            "dry_run": dry_run,
            "row_count": 0,
            "invalid_count": 1,
            "errors": [str(exc)],
            "state_path": str(target_path),
        }

    default_department = _normalize_department(department or payload.get("department") or "HR")
    call_rows: list[dict[str, Any]] = []
    invalid_count = 0
    for index, row in enumerate(payload["call_rows"], start=1):
        source_row = {**row, "source_file": row.get("source_file") or filename or ""}
        normalized = _normalize_call_row(source_row, config, row_number=index, default_department=default_department)
        if normalized:
            call_rows.append(normalized)
        else:
            invalid_count += 1

    analysis_reports: list[dict[str, Any]] = []
    for row in payload["analysis_reports"]:
        normalized = _normalize_analysis_report(row, config, default_department=default_department)
        if normalized:
            analysis_reports.append(normalized)
        else:
            invalid_count += 1

    lead_rows: list[dict[str, Any]] = []
    for row in payload["lead_rows"]:
        normalized = _normalize_lead_row(row, config, default_department=default_department)
        if normalized:
            lead_rows.append(normalized)

    activity_rows: list[dict[str, Any]] = []
    for index, row in enumerate(payload["activity_rows"], start=1):
        normalized = _normalize_activity_row(row, config, row_number=index, default_department=default_department)
        if normalized:
            activity_rows.append(normalized)
        else:
            invalid_count += 1

    existing = _read_state(target_path)
    merged_call_rows = _dedupe([*existing.call_rows, *call_rows], "call_id")
    merged_analysis_reports = _dedupe([*existing.analysis_reports, *analysis_reports], "analysis_file_key")
    merged_lead_rows = _dedupe([*existing.lead_rows, *lead_rows], "lead_key")
    merged_activity_rows = _dedupe([*existing.activity_rows, *activity_rows], "activity_id")

    imported_count = len(call_rows) + len(analysis_reports) + len(lead_rows) + len(activity_rows)
    if imported_count == 0:
        return {
            "status": "invalid",
            "source_authority": SOURCE_AUTHORITY,
            "projection_mode": PROJECTION_MODE,
            "dry_run": dry_run,
            "row_count": 0,
            "invalid_count": invalid_count or 1,
            "errors": ["hr_call_analysis_snapshot_contains_no_valid_rows"],
            "state_path": str(target_path),
        }

    if not dry_run:
        _write_state(
            target_path,
            call_rows=merged_call_rows,
            analysis_reports=merged_analysis_reports,
            lead_rows=merged_lead_rows,
            activity_rows=merged_activity_rows,
        )

    return {
        "status": "ok",
        "source_authority": SOURCE_AUTHORITY,
        "projection_mode": PROJECTION_MODE,
        "dry_run": dry_run,
        "row_count": imported_count,
        "department": default_department,
        "call_rows": len(call_rows),
        "analysis_reports": len(analysis_reports),
        "lead_rows": len(lead_rows),
        "activity_rows": len(activity_rows),
        "invalid_count": invalid_count,
        "errors": [],
        "state_path": str(target_path),
    }


def _employee_summary(
    call_rows: list[dict[str, Any]],
    config: HrCallAnalysisConfig,
    *,
    department: str = "HR",
) -> list[dict[str, Any]]:
    counters: dict[tuple[str, str], Counter] = defaultdict(Counter)
    parties: dict[tuple[str, str], set[str]] = defaultdict(set)
    active = _active_extensions_for_department(config, department)
    for row in call_rows:
        key = (_text(row.get("extension_id"), "unknown"), _text(row.get("employee_name"), "Unknown"))
        if active and key[0] not in active:
            continue
        counter = counters[key]
        counter["call_legs"] += 1
        counter["duration_seconds"] += int(row.get("duration_seconds") or 0)
        counter["voice_call_legs"] += int(row.get("is_voice_call") or 0)
        counter["outbound_legs"] += int(row.get("is_outbound_attempt") or 0)
        counter["connected_legs"] += int(row.get("is_connected") or 0)
        counter["not_connected_legs"] += int(row.get("is_not_connected") or 0)
        counter["voicemails"] += int(row.get("is_voicemail") or 0)
        counter["hangups"] += int(row.get("is_hangup") or 0)
        if row.get("external_party_hash"):
            parties[key].add(str(row["external_party_hash"]))

    rows: list[dict[str, Any]] = []
    max_voice = max((counter["voice_call_legs"] for counter in counters.values()), default=1) or 1
    max_minutes = max((counter["duration_seconds"] / 60 for counter in counters.values()), default=1) or 1
    for key, counter in counters.items():
        total = counter["call_legs"] or 1
        total_minutes = round(counter["duration_seconds"] / 60, 2)
        connected_rate = round(counter["connected_legs"] / total * 100, 2)
        voicemail_rate = round(counter["voicemails"] / total * 100, 2)
        hangup_rate = round(counter["hangups"] / total * 100, 2)
        no_connect_penalty = counter["not_connected_legs"] / total * 50
        quality_score = max(0, 100 - voicemail_rate - hangup_rate - no_connect_penalty)
        score = round(
            0.35 * (counter["voice_call_legs"] / max_voice * 100)
            + 0.25 * (total_minutes / max_minutes * 100)
            + 0.25 * quality_score
            + 0.15 * connected_rate,
            2,
        )
        rows.append(
            {
                "department": _normalize_department(department),
                "extension_id": key[0],
                "employee_name": key[1],
                "productivity_score_0_100": score,
                "call_legs": counter["call_legs"],
                "voice_call_legs": counter["voice_call_legs"],
                "distinct_external_parties": len(parties[key]),
                "total_minutes": total_minutes,
                "outbound_legs": counter["outbound_legs"],
                "connected_legs": counter["connected_legs"],
                "not_connected_legs": counter["not_connected_legs"],
                "voicemails": counter["voicemails"],
                "hangups": counter["hangups"],
                "connected_rate_pct": connected_rate,
                "voicemail_rate_pct": voicemail_rate,
                "hangup_rate_pct": hangup_rate,
            }
        )
    return sorted(rows, key=lambda row: row["productivity_score_0_100"], reverse=True)


def _monthly_employee_summary(
    call_rows: list[dict[str, Any]],
    config: HrCallAnalysisConfig,
    *,
    department: str = "HR",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for month in sorted({row.get("month") for row in call_rows if row.get("month")}):
        month_rows = [row for row in call_rows if row.get("month") == month]
        for employee in _employee_summary(month_rows, config, department=department):
            rows.append({"month": month, **employee})
    return rows


def _daily_volume(call_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counters: dict[str, Counter] = defaultdict(Counter)
    for row in call_rows:
        day = _text(row.get("call_date"))
        if not day:
            continue
        counter = counters[day]
        counter["call_legs"] += 1
        counter["outbound_attempts"] += int(row.get("is_outbound_attempt") or 0)
        counter["connected_calls"] += int(row.get("is_connected") or 0)
        counter["voicemails"] += int(row.get("is_voicemail") or 0)
        counter["duration_seconds"] += int(row.get("duration_seconds") or 0)
    return [
        {
            "date": day,
            "call_legs": counter["call_legs"],
            "outbound_attempts": counter["outbound_attempts"],
            "connected_calls": counter["connected_calls"],
            "voicemails": counter["voicemails"],
            "total_minutes": round(counter["duration_seconds"] / 60, 2),
        }
        for day, counter in sorted(counters.items())
    ]


def _activity_rows_for_selected_range(
    rows: list[dict[str, Any]],
    selected_range: DashboardDateRange | None,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    dated_rows = [
        (parsed.date(), row)
        for row in rows
        if (parsed := _parse_datetime(row.get("report_date")))
    ]
    if not dated_rows:
        return rows if not selected_range else []
    if selected_range:
        dated_rows = [(day, row) for day, row in dated_rows if selected_range.contains_date(day)]
        if not dated_rows:
            return []
    latest_day = max(day for day, _row in dated_rows)
    return [row for day, row in dated_rows if day == latest_day]


def _activity_summary(activity_rows: list[dict[str, Any]]) -> dict[str, Any]:
    report_dates = sorted({_text(row.get("report_date")) for row in activity_rows if row.get("report_date")})
    periods = sorted({_text(row.get("activity_period")) for row in activity_rows if row.get("activity_period")})
    return {
        "activity_calls": sum(int(row.get("activity_calls") or 0) for row in activity_rows),
        "activity_voicemails": sum(int(row.get("activity_voicemails") or 0) for row in activity_rows),
        "activity_hangups": sum(int(row.get("activity_hangups") or 0) for row in activity_rows),
        "activity_faxes": sum(int(row.get("activity_faxes") or 0) for row in activity_rows),
        "activity_voice_calls": sum(int(row.get("activity_voice_calls") or 0) for row in activity_rows),
        "activity_report_date": report_dates[-1] if report_dates else None,
        "activity_period": periods[-1] if periods else None,
    }


def _follow_up_rows(call_rows: list[dict[str, Any]], lead_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    outbound_by_party: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in call_rows:
        if row.get("is_outbound_attempt") and row.get("external_party_hash"):
            outbound_by_party[str(row["external_party_hash"])].append(row)
    rows: list[dict[str, Any]] = []
    for lead in lead_rows:
        assigned_at = _parse_datetime(lead.get("first_assigned_at"))
        if not assigned_at:
            continue
        calls = [
            call
            for call in outbound_by_party.get(str(lead.get("phone_hash")), [])
            if (_parse_datetime(call.get("call_started_at")) or assigned_at) >= assigned_at
        ]
        calls.sort(key=lambda call: call.get("call_started_at") or "")
        first_call_at = _parse_datetime(calls[0].get("call_started_at")) if calls else None
        first_call_hours = (
            round((first_call_at - assigned_at).total_seconds() / 3600, 2)
            if first_call_at
            else None
        )
        rows.append(
            {
                "lead_key": lead["lead_key"],
                "worklist": lead.get("worklist", "Unassigned"),
                "status": lead.get("status", "Active"),
                "assigned_at": _iso(assigned_at),
                "first_call_at": _iso(first_call_at),
                "first_call_hours": first_call_hours,
                "first_call_within_24h": bool(first_call_hours is not None and first_call_hours <= 24),
                "outbound_attempts": len(calls),
                "connected_calls": sum(int(call.get("is_connected") or 0) for call in calls),
                "voicemails": sum(int(call.get("is_voicemail") or 0) for call in calls),
                "last_call_at": calls[-1].get("call_started_at") if calls else None,
            }
        )
    return rows


def _call_period_metrics(
    call_rows: list[dict[str, Any]],
    follow_up_rows: list[dict[str, Any]],
) -> dict[str, int]:
    return {
        "call_volume": len(call_rows),
        "answered_calls": sum(int(row.get("is_connected") or 0) for row in call_rows),
        "missed_calls": sum(
            int(row.get("is_not_connected") or 0)
            + int(row.get("is_voicemail") or 0)
            + int(row.get("is_hangup") or 0)
            for row in call_rows
        ),
        "follow_ups": len(follow_up_rows),
    }


def _call_trend_comparison(
    *,
    all_call_rows: list[dict[str, Any]],
    all_lead_rows: list[dict[str, Any]],
    selected_range: DashboardDateRange | None,
) -> dict[str, Any] | None:
    if not selected_range:
        return None
    previous_range = selected_range.previous()
    current_calls = _filter_rows_for_date_range(
        all_call_rows,
        selected_range,
        ("call_started_at", "call_date", "created_at", "updated_at"),
    )
    current_leads = _filter_rows_for_date_range(
        all_lead_rows,
        selected_range,
        ("first_assigned_at", "assigned_at", "completed_at", "created_at", "updated_at"),
    )
    previous_calls = _filter_rows_for_date_range(
        all_call_rows,
        previous_range,
        ("call_started_at", "call_date", "created_at", "updated_at"),
    )
    previous_leads = _filter_rows_for_date_range(
        all_lead_rows,
        previous_range,
        ("first_assigned_at", "assigned_at", "completed_at", "created_at", "updated_at"),
    )
    current = _call_period_metrics(current_calls, _follow_up_rows(current_calls, current_leads))
    previous = _call_period_metrics(previous_calls, _follow_up_rows(previous_calls, previous_leads))
    return {
        "current": current,
        "previous": previous,
        "call_volume_change_pct": pct_change(current["call_volume"], previous["call_volume"]),
        "follow_up_change_pct": pct_change(current["follow_ups"], previous["follow_ups"]),
    }


def _coaching_flags(analysis_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for row in analysis_reports:
        reasons: list[str] = []
        sentiment = _text(row.get("sentiment")).casefold()
        if row.get("urgent"):
            reasons.append("urgent")
        if row.get("human_errors_detected"):
            reasons.append("human_error")
        if row.get("resolved") is False:
            reasons.append("unresolved")
        if sentiment in {"negative", "frustrated"}:
            reasons.append("negative_sentiment")
        if int(row.get("action_items_count") or 0) > 0:
            reasons.append("action_item")
        if reasons:
            flags.append(
                {
                    "analysis_file_key": row.get("analysis_file_key"),
                    "department": _row_department(row),
                    "call_date": row.get("call_date"),
                    "agent_name": row.get("agent_name"),
                    "category": row.get("category"),
                    "sentiment": row.get("sentiment"),
                    "resolved": row.get("resolved"),
                    "resolution_quality": row.get("resolution_quality"),
                    "action_items_count": row.get("action_items_count"),
                    "flag_reasons": ",".join(reasons),
                }
            )
    return sorted(flags, key=lambda row: (row.get("call_date") or "", row.get("analysis_file_key") or ""), reverse=True)


def build_hr_call_analysis_dataset(
    call_rows: list[dict[str, Any]],
    analysis_reports: list[dict[str, Any]],
    lead_rows: list[dict[str, Any]],
    activity_rows: list[dict[str, Any]] | None = None,
    *,
    now: datetime | None = None,
    config: HrCallAnalysisConfig | None = None,
    department: str = "HR",
    source_authority: str = SOURCE_AUTHORITY,
    source_status: str = "ok",
    source_message: str | None = None,
    last_imported_at: str | None = None,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
) -> dict[str, Any]:
    """Build dashboard-safe call analytics for one department."""

    config = config or HrCallAnalysisConfig.from_env()
    now = now or _now_utc()
    department = _normalize_department(department, default="HR")
    call_rows = _dedupe(call_rows, "call_id")
    analysis_reports = _dedupe(analysis_reports, "analysis_file_key")
    lead_rows = _dedupe(lead_rows, "lead_key")
    activity_rows = _dedupe(list(activity_rows or []), "activity_id")
    if department != "All":
        call_rows = [row for row in call_rows if _department_matches(row, department)]
        analysis_reports = [row for row in analysis_reports if _department_matches(row, department)]
        lead_rows = [row for row in lead_rows if _department_matches(row, department)]
        activity_rows = [row for row in activity_rows if _department_matches(row, department)]
    active_extensions = _active_extensions_for_department(config, department)
    call_rows = _filter_call_rows_for_active_extensions(call_rows, active_extensions)
    activity_rows = _filter_activity_rows_for_active_extensions(activity_rows, active_extensions)
    selected_range = dashboard_date_range(start_date, end_date)
    unfiltered_call_rows = call_rows
    unfiltered_lead_rows = lead_rows
    unfiltered_activity_rows = activity_rows
    call_rows = _filter_rows_for_date_range(
        call_rows,
        selected_range,
        ("call_started_at", "call_date", "created_at", "updated_at"),
    )
    analysis_reports = _filter_rows_for_date_range(
        analysis_reports,
        selected_range,
        ("call_started_at", "call_date", "created_at", "updated_at"),
    )
    lead_rows = _filter_rows_for_date_range(
        lead_rows,
        selected_range,
        ("first_assigned_at", "assigned_at", "completed_at", "created_at", "updated_at"),
    )
    activity_rows = _activity_rows_for_selected_range(activity_rows, selected_range)
    activity_summary = _activity_summary(activity_rows)

    total_duration = sum(int(row.get("duration_seconds") or 0) for row in call_rows)
    outbound_attempts = sum(int(row.get("is_outbound_attempt") or 0) for row in call_rows)
    connected_calls = sum(int(row.get("is_connected") or 0) for row in call_rows)
    voicemails = sum(int(row.get("is_voicemail") or 0) for row in call_rows)
    hangups = sum(int(row.get("is_hangup") or 0) for row in call_rows)
    missed_calls = sum(int(row.get("is_not_connected") or 0) for row in call_rows) + voicemails + hangups
    follow_up = _follow_up_rows(call_rows, lead_rows)
    first_call_eligible = len(follow_up)
    first_call_within_24h = sum(1 for row in follow_up if row["first_call_within_24h"])
    stale_no_call_48h = 0
    for row in follow_up:
        assigned_at = _parse_datetime(row.get("assigned_at"))
        if row["first_call_at"] or not assigned_at:
            continue
        if (now - assigned_at).total_seconds() >= 48 * 3600:
            stale_no_call_48h += 1

    employee_productivity = _employee_summary(call_rows, config, department=department)
    coaching_flags = _coaching_flags(analysis_reports)
    coverage_dates = [_parse_datetime(row.get("call_started_at")) for row in call_rows]
    coverage_dates = [value for value in coverage_dates if value]
    return {
        "generated_at": now.isoformat(),
        "projection_mode": PROJECTION_MODE,
        "source_system": SOURCE_SYSTEM,
        "source_authority": source_authority,
        "department": department,
        "department_key": _department_key(department),
        "source_status": source_status,
        "source_message": source_message,
        "last_imported_at": last_imported_at,
        "date_range": selected_range.as_dict() if selected_range else None,
        "pii_suppressed": True,
        "phone_numbers_stored": False,
        "active_extensions": list(config.active_extensions),
        "coverage": {
            "start": _iso(min(coverage_dates)) if coverage_dates else None,
            "end": _iso(max(coverage_dates)) if coverage_dates else None,
            "months": sorted({row.get("month") for row in call_rows if row.get("month")}),
        },
        "summary": {
            "total_call_legs": len(call_rows),
            **activity_summary,
            "total_minutes": round(total_duration / 60, 2),
            "avg_call_seconds": round(total_duration / len(call_rows), 2) if call_rows else 0,
            "outbound_attempts": outbound_attempts,
            "answered_calls": connected_calls,
            "missed_calls": missed_calls,
            "connected_calls": connected_calls,
            "connect_rate_pct": round(connected_calls / outbound_attempts * 100, 2) if outbound_attempts else None,
            "voicemails": voicemails,
            "hangups": hangups,
            "active_employee_count": len(employee_productivity),
            "analysis_reports": len(analysis_reports),
            "coaching_flags": len(coaching_flags),
            "urgent_flags": sum(1 for row in analysis_reports if row.get("urgent")),
            "unresolved_calls": sum(1 for row in analysis_reports if row.get("resolved") is False),
            "human_error_reports": sum(1 for row in analysis_reports if row.get("human_errors_detected")),
            "first_call_eligible_leads": first_call_eligible,
            "first_call_within_24h": first_call_within_24h,
            "first_call_24h_pct": round(first_call_within_24h / first_call_eligible, 4) if first_call_eligible else None,
            "stale_no_call_48h": stale_no_call_48h,
            "follow_up_count": len(follow_up),
        },
        "trend_comparison": _call_trend_comparison(
            all_call_rows=unfiltered_call_rows,
            all_lead_rows=unfiltered_lead_rows,
            selected_range=selected_range,
        ),
        "employee_productivity": employee_productivity,
        "monthly_employee_productivity": _monthly_employee_summary(call_rows, config, department=department),
        "daily_volume": _daily_volume(call_rows),
        "follow_up": follow_up,
        "coaching_flags": coaching_flags,
        "row_counts": {
            "call_rows": len(call_rows),
            "unfiltered_call_rows": len(unfiltered_call_rows),
            "analysis_reports": len(analysis_reports),
            "lead_rows": len(lead_rows),
            "activity_rows": len(activity_rows),
            "unfiltered_activity_rows": len(unfiltered_activity_rows),
            "follow_up_rows": len(follow_up),
            "employee_rows": len(employee_productivity),
            "coaching_flag_rows": len(coaching_flags),
        },
        "validation_notes": [
            "First-call SLA requires phone-hash overlap between recruiting leads and call logs.",
            "Activity Calls come from the Grasshopper Activity summary; Detail rows are call-leg evidence.",
            "Raw phone numbers are not exposed in FleetPulse payloads.",
        ],
    }


async def get_hr_call_analysis_dataset(
    *,
    now: datetime | None = None,
    config: HrCallAnalysisConfig | None = None,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
) -> dict[str, Any]:
    config = config or HrCallAnalysisConfig.from_env()
    source = _read_state(Path(config.state_path))
    return build_hr_call_analysis_dataset(
        source.call_rows,
        source.analysis_reports,
        source.lead_rows,
        source.activity_rows,
        now=now,
        config=config,
        source_status=source.status,
        source_message=source.message,
        last_imported_at=source.last_imported_at,
        start_date=start_date,
        end_date=end_date,
    )


def _configured_department_names(
    config: HrCallAnalysisConfig,
    call_rows: list[dict[str, Any]],
    analysis_reports: list[dict[str, Any]],
    lead_rows: list[dict[str, Any]],
    activity_rows: list[dict[str, Any]] | None = None,
) -> list[str]:
    departments = {_normalize_department(department) for department in config.departments}
    for row in [*call_rows, *analysis_reports, *lead_rows, *list(activity_rows or [])]:
        departments.add(_row_department(row))
    return sorted(departments, key=lambda value: (value != "Operations", value != "HR", value))


def _department_rollups(
    call_rows: list[dict[str, Any]],
    analysis_reports: list[dict[str, Any]],
    lead_rows: list[dict[str, Any]],
    activity_rows: list[dict[str, Any]] | None = None,
    *,
    now: datetime,
    config: HrCallAnalysisConfig,
    source_status: str,
    source_message: str | None,
    last_imported_at: str | None,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
) -> list[dict[str, Any]]:
    rollups: list[dict[str, Any]] = []
    for department in _configured_department_names(config, call_rows, analysis_reports, lead_rows, activity_rows):
        dataset = build_hr_call_analysis_dataset(
            call_rows,
            analysis_reports,
            lead_rows,
            activity_rows,
            now=now,
            config=config,
            department=department,
            source_authority=DEPARTMENT_SOURCE_AUTHORITY,
            source_status=source_status,
            source_message=source_message,
            last_imported_at=last_imported_at,
            start_date=start_date,
            end_date=end_date,
        )
        rollups.append(
            {
                "department": department,
                "department_key": _department_key(department),
                "source_status": dataset["source_status"],
                "coverage": dataset["coverage"],
                "summary": dataset["summary"],
                "row_counts": dataset["row_counts"],
                "top_employees": dataset["employee_productivity"][:5],
                "coaching_flags": dataset["coaching_flags"][:5],
            }
        )
    return rollups


async def get_department_call_analysis_dataset(
    department: str | None = None,
    *,
    now: datetime | None = None,
    config: HrCallAnalysisConfig | None = None,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
) -> dict[str, Any]:
    config = config or HrCallAnalysisConfig.from_env()
    now = now or _now_utc()
    source = _read_state(Path(config.state_path))
    selected_department = _normalize_department(department or "All", default="All")
    dataset = build_hr_call_analysis_dataset(
        source.call_rows,
        source.analysis_reports,
        source.lead_rows,
        source.activity_rows,
        now=now,
        config=config,
        department=selected_department,
        source_authority=DEPARTMENT_SOURCE_AUTHORITY,
        source_status=source.status,
        source_message=source.message,
        last_imported_at=source.last_imported_at,
        start_date=start_date,
        end_date=end_date,
    )
    rollups = _department_rollups(
        source.call_rows,
        source.analysis_reports,
        source.lead_rows,
        source.activity_rows,
        now=now,
        config=config,
        source_status=source.status,
        source_message=source.message,
        last_imported_at=source.last_imported_at,
        start_date=start_date,
        end_date=end_date,
    )
    dataset["configured_departments"] = [rollup["department"] for rollup in rollups]
    dataset["department_rollups"] = rollups
    return dataset


def validate_hr_call_analysis_import_api_key(provided: str | None, config: HrCallAnalysisConfig | None = None) -> None:
    config = config or HrCallAnalysisConfig.from_env()
    if config.import_api_key and provided != config.import_api_key:
        raise PermissionError("Invalid HR call analysis import API key")


def validate_hr_call_analysis_sync_api_key(config: HrCallAnalysisConfig, supplied_key: str | None) -> None:
    if config.sync_api_key and supplied_key != config.sync_api_key:
        raise PermissionError("invalid_hr_call_analysis_sync_key")


def hr_call_analysis_status(config: HrCallAnalysisConfig | None = None) -> dict[str, Any]:
    config = config or HrCallAnalysisConfig.from_env()
    state = _read_state(Path(config.state_path))
    return {
        **config.safe_status(),
        "source_status": state.status,
        "source_message": state.message,
        "last_imported_at": state.last_imported_at,
        "row_counts": {
            "call_rows": len(state.call_rows),
            "analysis_reports": len(state.analysis_reports),
            "lead_rows": len(state.lead_rows),
            "activity_rows": len(state.activity_rows),
        },
    }


def department_call_analysis_status(config: HrCallAnalysisConfig | None = None) -> dict[str, Any]:
    config = config or HrCallAnalysisConfig.from_env()
    state = _read_state(Path(config.state_path))
    departments = _configured_department_names(
        config,
        state.call_rows,
        state.analysis_reports,
        state.lead_rows,
        state.activity_rows,
    )
    return {
        **config.safe_status(),
        "source_authority": DEPARTMENT_SOURCE_AUTHORITY,
        "source_status": state.status,
        "source_message": state.message,
        "last_imported_at": state.last_imported_at,
        "configured_departments": departments,
        "row_counts": {
            "call_rows": len(state.call_rows),
            "analysis_reports": len(state.analysis_reports),
            "lead_rows": len(state.lead_rows),
            "activity_rows": len(state.activity_rows),
        },
    }


def sync_hr_call_analysis_sharepoint_folder(
    config: HrCallAnalysisConfig | None = None,
    *,
    client: SharePointDriveClient | None = None,
    dry_run: bool = False,
    department: str | None = None,
) -> HrCallAnalysisSyncResult:
    config = config or HrCallAnalysisConfig.from_env()
    if not config.sync_ready:
        missing = ",".join(config.missing_sync_config())
        raise HrCallAnalysisConfigError(f"hr_call_analysis_sharepoint_sync_not_configured:{missing}")

    graph_client = client or SharePointDriveClient(config)  # type: ignore[arg-type]
    files = graph_client.list_files()
    selected_department = _normalize_department(
        department or _department_from_values((config.folder_path,), default="HR")
    )
    file_results: list[HrCallAnalysisFileSyncResult] = []
    errors: list[str] = []
    imported_count = 0
    duplicate_count = 0
    invalid_count = 0

    before = _read_state(Path(config.state_path))
    before_keys = {row.get("analysis_file_key") for row in before.analysis_reports}
    for file in files:
        file_key = _hash_key((file.name, str(file.last_modified_at), str(file.size)))
        try:
            content = graph_client.download_file_text(file)
            result = import_hr_call_analysis_snapshot(
                json.dumps(
                    {
                        "department": selected_department,
                        "analysis_reports": [
                            {
                                "analysis_text": content,
                                "filename": file.name,
                                "department": selected_department,
                                "created_at": _iso(file.last_modified_at),
                                "updated_at": _iso(file.last_modified_at),
                                "size_bytes": file.size,
                                "source_folder": config.folder_path,
                            }
                        ]
                    }
                ),
                filename="sharepoint-hr-call-analysis.json",
                dry_run=dry_run,
                department=selected_department,
                config=config,
            )
            imported = int(result.get("analysis_reports") or 0)
            duplicate = 1 if file_key in before_keys else 0
            invalid = int(result.get("invalid_count") or 0)
            file_errors = list(result.get("errors") or [])
        except Exception as exc:  # noqa: BLE001
            imported = 0
            duplicate = 0
            invalid = 1
            file_errors = [f"{file_key}: {type(exc).__name__}"]
        file_result = HrCallAnalysisFileSyncResult(
            analysis_file_key=file_key,
            last_modified_at=_iso(file.last_modified_at),
            imported_count=imported,
            duplicate_count=duplicate,
            invalid_count=invalid,
            errors=file_errors,
        )
        file_results.append(file_result)
        imported_count += imported
        duplicate_count += duplicate
        invalid_count += invalid
        errors.extend(file_errors)

    return HrCallAnalysisSyncResult(
        status="ok" if not errors else "partial",
        dry_run=dry_run,
        folder_path=config.folder_path,
        fetched_count=len(files),
        imported_count=imported_count,
        duplicate_count=duplicate_count,
        invalid_count=invalid_count,
        errors=errors,
        files=file_results,
    )


def sync_department_call_analysis_sharepoint_folders(
    config: HrCallAnalysisConfig | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    config = config or HrCallAnalysisConfig.from_env()
    folder_map = config.department_folder_paths or {"HR": config.folder_path}
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    imported_count = 0
    duplicate_count = 0
    invalid_count = 0
    fetched_count = 0

    for department, folder_path in folder_map.items():
        folder_config = replace(
            config,
            folder_path=folder_path,
            source_file_urls=() if config.department_folder_paths else config.source_file_urls,
        )
        try:
            result = sync_hr_call_analysis_sharepoint_folder(
                folder_config,
                dry_run=dry_run,
                department=department,
            )
            payload = result.as_dict()
            payload["department"] = _normalize_department(department)
            results.append(payload)
            imported_count += result.imported_count
            duplicate_count += result.duplicate_count
            invalid_count += result.invalid_count
            fetched_count += result.fetched_count
            errors.extend(result.errors)
        except Exception as exc:  # noqa: BLE001
            error = f"{_normalize_department(department)}:{type(exc).__name__}"
            errors.append(error)
            results.append(
                {
                    "status": "failed",
                    "department": _normalize_department(department),
                    "folder_path": folder_path,
                    "errors": [error],
                    "fetched_count": 0,
                    "imported_count": 0,
                    "duplicate_count": 0,
                    "invalid_count": 1,
                    "files": [],
                }
            )
            invalid_count += 1

    return {
        "status": "ok" if not errors else "partial",
        "source_authority": DEPARTMENT_SOURCE_AUTHORITY,
        "projection_mode": PROJECTION_MODE,
        "dry_run": dry_run,
        "department_count": len(folder_map),
        "fetched_count": fetched_count,
        "imported_count": imported_count,
        "duplicate_count": duplicate_count,
        "invalid_count": invalid_count,
        "errors": errors,
        "departments": results,
    }
