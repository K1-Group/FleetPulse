"""Read-only HR recruiting KPI workbook projection.

The workbook parser only projects source-backed aggregate evidence. It never
returns applicant names, phone numbers, or email addresses to FleetPulse.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.workbook.workbook import Workbook

SOURCE_PROFILE = "kpi_workbook"
SOURCE_SYSTEM = "HR Lead KPI Recheck workbook"
SOURCE_AUTHORITY = "Grasshopper/SharePoint/Tenstreet HR KPI recheck workbook"

EXPECTED_TABS = (
    "Lead Level KPI",
    "Call Attempts Detail",
    "Failed No Outbound",
    "Recovered 24-48h",
    "Failed Over 72h",
    "No Real Discussion",
    "Source Log QA",
)

FIRST_OUTREACH_BUCKET_ORDER = (
    "Within 24h",
    "24-48h recovered",
    "48-72h late",
    "Over 72h failed",
    "No outbound found",
)
REAL_DISCUSSION_BUCKET_ORDER = (
    "Within 24h",
    "24-48h recovered",
    "48-72h late",
    "Over 72h failed",
    "No 1min+ discussion found",
)


def build_hr_recruiting_workbook_dataset(
    workbook_path: str,
    *,
    now: datetime,
    source: str,
    table_id: str,
    sla_hours: tuple[int, ...],
    hard_targets: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build the HR recruiting dataset from the KPI recheck workbook."""

    path = Path(workbook_path).expanduser()
    if not workbook_path:
        return _empty_dataset(
            now=now,
            source=source,
            table_id=table_id,
            sla_hours=sla_hours,
            hard_targets=hard_targets,
            source_status="snapshot_not_configured",
            source_message="Configure HR_RECRUITING_WORKBOOK_PATH with the approved HR KPI recheck workbook.",
        )
    if not path.exists():
        return _empty_dataset(
            now=now,
            source=source,
            table_id=table_id,
            sla_hours=sla_hours,
            hard_targets=hard_targets,
            source_status="source_error",
            source_message="Configured HR_RECRUITING_WORKBOOK_PATH does not exist.",
            workbook_name=path.name,
        )

    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - keep dashboard status available.
        return _empty_dataset(
            now=now,
            source=source,
            table_id=table_id,
            sla_hours=sla_hours,
            hard_targets=hard_targets,
            source_status="source_error",
            source_message=f"HR KPI workbook could not be opened: {type(exc).__name__}.",
            workbook_name=path.name,
        )

    present_tabs = [sheet for sheet in EXPECTED_TABS if sheet in workbook.sheetnames]
    missing_tabs = [sheet for sheet in EXPECTED_TABS if sheet not in workbook.sheetnames]
    if "Lead Level KPI" not in workbook.sheetnames:
        return _empty_dataset(
            now=now,
            source=source,
            table_id=table_id,
            sla_hours=sla_hours,
            hard_targets=hard_targets,
            source_status="source_error",
            source_message="HR KPI workbook is missing required tab: Lead Level KPI.",
            workbook_name=path.name,
            present_tabs=present_tabs,
            missing_tabs=missing_tabs,
        )

    leads = _records_for_sheet(
        workbook,
        "Lead Level KPI",
        required_headers=("Lead Created At", "First Outreach KPI Bucket", "Real Discussion KPI Bucket"),
    )
    call_attempts = _records_for_sheet(
        workbook,
        "Call Attempts Detail",
        required_headers=("Call Date/Time", "HR Member", "Duration Seconds"),
    )
    first_outreach_by_member = _member_kpi_rows(
        _records_for_sheet(workbook, "KPI By First Outreach", required_headers=("HR Member", "Within_24h"))
    )
    real_discussion_by_member = _member_kpi_rows(
        _records_for_sheet(workbook, "KPI By Real Discussion", required_headers=("HR Member", "Within_24h"))
    )
    source_log_qa = _source_log_qa_rows(
        _records_for_sheet(workbook, "Source Log QA", required_headers=("File", "Rows", "Used for Mapping"))
    )

    if not leads:
        return _empty_dataset(
            now=now,
            source=source,
            table_id=table_id,
            sla_hours=sla_hours,
            hard_targets=hard_targets,
            source_status="empty",
            source_message="HR KPI workbook is present but Lead Level KPI contains no rows.",
            workbook_name=path.name,
            present_tabs=present_tabs,
            missing_tabs=missing_tabs,
        )

    as_of = _ensure_aware(now)
    source_status = "partial" if missing_tabs else "ok"
    source_message = (
        f"HR KPI workbook is missing optional evidence tab(s): {', '.join(missing_tabs)}."
        if missing_tabs
        else None
    )

    first_outreach_counts = Counter(_text(row.get("First Outreach KPI Bucket"), "Unknown") for row in leads)
    real_discussion_counts = Counter(_text(row.get("Real Discussion KPI Bucket"), "Unknown") for row in leads)
    status_counts = Counter(_text(row.get("App Status"), "No Status") for row in leads)
    lead_count = len(leads)
    within_24h = first_outreach_counts.get("Within 24h", 0)
    recovered_24_48 = first_outreach_counts.get("24-48h recovered", 0)
    late_48_72 = first_outreach_counts.get("48-72h late", 0)
    failed_over_72 = first_outreach_counts.get("Over 72h failed", 0)
    no_outbound = first_outreach_counts.get("No outbound found", 0)
    no_real_discussion = real_discussion_counts.get("No 1min+ discussion found", 0)
    first_touch_pct = round(within_24h / lead_count, 4) if lead_count else None
    first_outreach_hours = [
        value
        for value in (_number(row.get("Hours to First Outreach")) for row in leads)
        if value is not None
    ]
    real_discussion_hours = [
        value
        for value in (_number(row.get("Hours to First Real Discussion")) for row in leads)
        if value is not None
    ]
    source_rows_by_tab = _tab_counts(workbook, present_tabs)
    kpi_summary = {
        "unique_lead_forms": lead_count,
        "outbound_within_24h": within_24h,
        "outbound_24_48h": recovered_24_48,
        "outbound_48_72h": late_48_72,
        "outbound_over_72h": failed_over_72,
        "no_outbound_found": no_outbound,
        "any_outbound_after_form": lead_count - no_outbound,
        "no_real_discussion_found": no_real_discussion,
        "real_discussion_within_24h": real_discussion_counts.get("Within 24h", 0),
        "total_outbound_attempts": len(call_attempts),
        "total_1min_discussions": sum(1 for row in call_attempts if _boolish(row.get("Real Discussion 1min+"))),
        "avg_hours_to_first_outreach": _mean(first_outreach_hours),
        "avg_hours_to_first_real_discussion": _mean(real_discussion_hours),
        "first_touch_24h_pct": first_touch_pct,
    }

    summary = {
        "active_leads": lead_count,
        "new_leads_today": sum(1 for row in leads if _same_day(row.get("Lead Created At"), as_of)),
        "avg_process_age_hours": kpi_summary["avg_hours_to_first_outreach"],
        "stale_leads": late_48_72 + failed_over_72 + no_outbound,
        "completed_today": 0,
        "new_hires_7d": 0,
        "active_qualified_pipeline": 0,
        "first_touch_24h_pct": first_touch_pct,
        "first_touch_eligible_count": lead_count,
        "first_touch_within_24h_count": within_24h,
        "stale_untouched_48h": no_outbound,
        "orientation_scheduled_count": 0,
        "orientation_show_count": 0,
        "orientation_show_rate": None,
    }
    hard_target_results = _build_hard_target_results(
        hard_targets,
        {
            "new_hires_7d": None,
            "active_qualified_pipeline": None,
            "first_touch_24h_pct": first_touch_pct,
            "stale_untouched_48h": no_outbound,
            "orientation_show_rate": None,
        },
        {
            "new_hires_7d": False,
            "active_qualified_pipeline": False,
            "first_touch_24h_pct": lead_count > 0,
            "stale_untouched_48h": lead_count > 0,
            "orientation_show_rate": False,
        },
    )
    hard_target_misses = [key for key, target in hard_target_results.items() if target["status"] == "warning"]
    hard_target_pending = [key for key, target in hard_target_results.items() if target["status"] == "awaiting_feed"]
    hard_target_status = (
        "awaiting_feed"
        if hard_target_pending and not hard_target_misses
        else "healthy" if not hard_target_misses and not hard_target_pending else "warning"
    )

    return {
        "generated_at": as_of.isoformat(),
        "projection_mode": "read_only",
        "source_profile": SOURCE_PROFILE,
        "source_system": SOURCE_SYSTEM,
        "source_authority": SOURCE_AUTHORITY,
        "source": source,
        "table_id": table_id,
        "source_artifact": path.name,
        "source_status": source_status,
        "source_message": source_message,
        "pii_suppressed": True,
        "sla_hours": list(sla_hours),
        "hard_targets": hard_target_results,
        "hard_target_status": hard_target_status,
        "hard_target_misses": hard_target_misses,
        "hard_target_pending": hard_target_pending,
        "summary": summary,
        "by_worklist": _first_outreach_bucket_rows(leads, first_outreach_counts),
        "daily": _daily_rows(leads),
        "status_counts": [
            {"status": status, "count": count}
            for status, count in sorted(status_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "trend": _trend_rows(leads),
        "row_counts": {
            "source_rows": lead_count,
            "deduped_leads": lead_count,
            "active_leads": lead_count,
            "completed_leads": 0,
            "invalid_rows": 0,
            "source_email_dedupe_rows": 0,
            "call_attempt_rows": len(call_attempts),
            "source_log_qa_rows": len(source_log_qa),
            "tabs_present": len(present_tabs),
            "tabs_missing": len(missing_tabs),
        },
        "validation_errors": {"missing_tabs": len(missing_tabs)} if missing_tabs else {},
        "workbook_evidence": {
            "workbook_name": path.name,
            "tabs": source_rows_by_tab,
            "missing_tabs": missing_tabs,
            "kpi_summary": kpi_summary,
            "first_outreach_buckets": _bucket_counts(first_outreach_counts, FIRST_OUTREACH_BUCKET_ORDER),
            "real_discussion_buckets": _bucket_counts(real_discussion_counts, REAL_DISCUSSION_BUCKET_ORDER),
            "first_outreach_by_member": first_outreach_by_member,
            "real_discussion_by_member": real_discussion_by_member,
            "source_log_qa": source_log_qa,
        },
    }


def _empty_dataset(
    *,
    now: datetime,
    source: str,
    table_id: str,
    sla_hours: tuple[int, ...],
    hard_targets: dict[str, dict[str, Any]],
    source_status: str,
    source_message: str,
    workbook_name: str | None = None,
    present_tabs: list[str] | None = None,
    missing_tabs: list[str] | None = None,
) -> dict[str, Any]:
    as_of = _ensure_aware(now)
    hard_target_results = _build_hard_target_results(
        hard_targets,
        {key: None for key in hard_targets},
        {key: False for key in hard_targets},
    )
    return {
        "generated_at": as_of.isoformat(),
        "projection_mode": "read_only",
        "source_profile": SOURCE_PROFILE,
        "source_system": SOURCE_SYSTEM,
        "source_authority": SOURCE_AUTHORITY,
        "source": source,
        "table_id": table_id,
        "source_artifact": workbook_name,
        "source_status": source_status,
        "source_message": source_message,
        "pii_suppressed": True,
        "sla_hours": list(sla_hours),
        "hard_targets": hard_target_results,
        "hard_target_status": "awaiting_feed",
        "hard_target_misses": [],
        "hard_target_pending": list(hard_targets),
        "summary": {
            "active_leads": 0,
            "new_leads_today": 0,
            "avg_process_age_hours": 0,
            "stale_leads": 0,
            "completed_today": 0,
            "new_hires_7d": 0,
            "active_qualified_pipeline": 0,
            "first_touch_24h_pct": None,
            "first_touch_eligible_count": 0,
            "first_touch_within_24h_count": 0,
            "stale_untouched_48h": 0,
            "orientation_scheduled_count": 0,
            "orientation_show_count": 0,
            "orientation_show_rate": None,
        },
        "by_worklist": [],
        "daily": [],
        "status_counts": [],
        "trend": [],
        "row_counts": {
            "source_rows": 0,
            "deduped_leads": 0,
            "active_leads": 0,
            "completed_leads": 0,
            "invalid_rows": 0,
            "source_email_dedupe_rows": 0,
            "call_attempt_rows": 0,
            "source_log_qa_rows": 0,
            "tabs_present": len(present_tabs or []),
            "tabs_missing": len(missing_tabs or EXPECTED_TABS),
        },
        "validation_errors": {"missing_tabs": len(missing_tabs or EXPECTED_TABS)},
        "workbook_evidence": {
            "workbook_name": workbook_name,
            "tabs": [
                {"sheet": sheet, "row_count": 0, "status": "present"}
                for sheet in (present_tabs or [])
            ],
            "missing_tabs": list(missing_tabs or EXPECTED_TABS),
            "kpi_summary": {},
            "first_outreach_buckets": [],
            "real_discussion_buckets": [],
            "first_outreach_by_member": [],
            "real_discussion_by_member": [],
            "source_log_qa": [],
        },
    }


def _records_for_sheet(
    workbook: Workbook,
    sheet_name: str,
    *,
    required_headers: tuple[str, ...],
) -> list[dict[str, Any]]:
    if sheet_name not in workbook.sheetnames:
        return []

    worksheet = workbook[sheet_name]
    header_row_index = _find_header_row(worksheet, required_headers)
    if header_row_index is None:
        return []

    headers = [
        _text(cell)
        for cell in next(worksheet.iter_rows(min_row=header_row_index, max_row=header_row_index, values_only=True))
    ]
    records: list[dict[str, Any]] = []
    for row in worksheet.iter_rows(min_row=header_row_index + 1, values_only=True):
        if not any(value not in (None, "") for value in row):
            continue
        record = {
            header: value
            for header, value in zip(headers, row)
            if header
        }
        if any(value not in (None, "") for value in record.values()):
            records.append(record)
    return records


def _find_header_row(worksheet: Any, required_headers: tuple[str, ...]) -> int | None:
    required = {_normalize_header(header) for header in required_headers}
    best: tuple[int, int] | None = None
    max_row = min(20, int(worksheet.max_row or 0))
    for index, row in enumerate(worksheet.iter_rows(min_row=1, max_row=max_row, values_only=True), start=1):
        normalized = {_normalize_header(_text(value)) for value in row if _text(value)}
        score = len(required.intersection(normalized))
        if score and (best is None or score > best[0]):
            best = (score, index)
    if best and best[0] >= min(2, len(required)):
        return best[1]
    return None


def _tab_counts(workbook: Workbook, present_tabs: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sheet in present_tabs:
        required = {
            "Source Log QA": ("File", "Rows", "Used for Mapping"),
            "Call Attempts Detail": ("Call Date/Time", "HR Member", "Duration Seconds"),
        }.get(sheet, ("Lead Created At", "First Outreach KPI Bucket", "Real Discussion KPI Bucket"))
        records = _records_for_sheet(workbook, sheet, required_headers=required)
        rows.append({"sheet": sheet, "row_count": len(records), "status": "present"})
    return rows


def _first_outreach_bucket_rows(
    leads: list[dict[str, Any]],
    first_outreach_counts: Counter[str],
) -> list[dict[str, Any]]:
    hours_by_bucket: dict[str, list[float]] = defaultdict(list)
    for row in leads:
        bucket = _text(row.get("First Outreach KPI Bucket"), "Unknown")
        hours = _number(row.get("Hours to First Outreach"))
        if hours is not None:
            hours_by_bucket[bucket].append(hours)

    ordered = _bucket_counts(first_outreach_counts, FIRST_OUTREACH_BUCKET_ORDER)
    rows: list[dict[str, Any]] = []
    for item in ordered:
        bucket = item["bucket"]
        count = item["count"]
        stale_24h = count if bucket in {"24-48h recovered", "48-72h late", "Over 72h failed", "No outbound found"} else 0
        stale_48h = count if bucket in {"48-72h late", "Over 72h failed", "No outbound found"} else 0
        stale_72h = count if bucket in {"Over 72h failed", "No outbound found"} else 0
        rows.append(
            {
                "worklist": bucket,
                "active_leads": count,
                "new_leads_today": 0,
                "avg_age_hours": _mean(hours_by_bucket.get(bucket, [])),
                "max_age_hours": _max_or_zero(hours_by_bucket.get(bucket, [])),
                "stale_24h": stale_24h,
                "stale_48h": stale_48h,
                "stale_72h": stale_72h,
            }
        )
    return rows


def _daily_rows(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"new_leads": 0, "completed_leads": 0, "active_leads": 0, "process_times": []}
    )
    for row in leads:
        lead_date = _parse_datetime(row.get("Lead Created At"))
        if lead_date is None:
            continue
        bucket = _text(row.get("First Outreach KPI Bucket"), "Unknown")
        key = (lead_date.date().isoformat(), bucket)
        buckets[key]["new_leads"] += 1
        buckets[key]["active_leads"] += 1
        if _text(row.get("Real Discussion KPI Bucket")) not in {"", "No 1min+ discussion found"}:
            buckets[key]["completed_leads"] += 1
        hours = _number(row.get("Hours to First Outreach"))
        if hours is not None:
            buckets[key]["process_times"].append(hours)

    rows: list[dict[str, Any]] = []
    for (day, bucket), values in buckets.items():
        rows.append(
            {
                "date": day,
                "worklist": bucket,
                "new_leads": values["new_leads"],
                "completed_leads": values["completed_leads"],
                "active_leads": values["active_leads"],
                "avg_process_time_hours": _mean(values["process_times"]),
            }
        )
    return sorted(rows, key=lambda row: (str(row["date"]), str(row["worklist"])))


def _trend_rows(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {"new_leads": 0, "stale_leads": 0, "ages": []})
    for row in leads:
        lead_date = _parse_datetime(row.get("Lead Created At"))
        if lead_date is None:
            continue
        day = lead_date.date().isoformat()
        buckets[day]["new_leads"] += 1
        bucket = _text(row.get("First Outreach KPI Bucket"))
        if bucket in {"48-72h late", "Over 72h failed", "No outbound found"}:
            buckets[day]["stale_leads"] += 1
        hours = _number(row.get("Hours to First Outreach"))
        if hours is not None:
            buckets[day]["ages"].append(hours)

    rows: list[dict[str, Any]] = []
    for day, values in buckets.items():
        rows.append(
            {
                "date": day,
                "active_leads": values["new_leads"],
                "new_leads": values["new_leads"],
                "stale_leads": values["stale_leads"],
                "avg_age_hours": _mean(values["ages"]),
            }
        )
    return sorted(rows, key=lambda row: str(row["date"]))


def _member_kpi_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        member = _text(record.get("HR Member"))
        if not member:
            continue
        rows.append(
            {
                "hr_member": member,
                "lead_count": _int(record.get("Leads_First_Outreach") or record.get("Leads_First_Real_Discussion")),
                "within_24h": _int(record.get("Within_24h")),
                "recovered_24_48h": _int(record.get("Recovered_24_48")),
                "late_48_72h": _int(record.get("Late_48_72")),
                "failed_over_72h": _int(record.get("Failed_Over_72")),
                "avg_hours": _number(record.get("Avg_Hours_To_First_Outreach") or record.get("Avg_Hours_To_First_Real")),
                "median_hours": _number(record.get("Median_Hours_To_First_Outreach") or record.get("Median_Hours_To_First_Real")),
                "within_24h_rate": _number(record.get("Within_24h_Rate") or record.get("Real_Within_24_Rate")),
                "total_outbound_attempts": _int(record.get("Total_Outbound_Attempts")),
            }
        )
    return rows


def _source_log_qa_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        file_name = _text(record.get("File"))
        if not file_name:
            continue
        rows.append(
            {
                "file": file_name,
                "row_count": _int(record.get("Rows")),
                "column_count": _int(record.get("Columns")),
                "used_for_mapping": _boolish(record.get("Used for Mapping")),
                "notes": _text(record.get("Reason / Notes")),
                "first_columns": _text(record.get("First Columns")),
            }
        )
    return rows


def _bucket_counts(counter: Counter[str], order: tuple[str, ...]) -> list[dict[str, Any]]:
    ordered_keys = [key for key in order if key in counter]
    ordered_keys.extend(sorted(key for key in counter if key not in ordered_keys))
    return [{"bucket": key, "count": int(counter[key])} for key in ordered_keys]


def _build_hard_target_results(
    hard_targets: dict[str, dict[str, Any]],
    actuals: dict[str, int | float | None],
    evidence_available: dict[str, bool],
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for key, spec in hard_targets.items():
        actual = actuals.get(key)
        can_evaluate = evidence_available.get(key, actual is not None) and actual is not None
        status = (
            "awaiting_feed"
            if not can_evaluate
            else "healthy"
            if _target_met(float(actual), str(spec["operator"]), float(spec["target"]))
            else "warning"
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


def _target_met(actual: float, operator: str, target: float) -> bool:
    if operator == ">=":
        return actual >= target
    if operator == "<=":
        return actual <= target
    return actual == target


def _normalize_header(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


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
    if isinstance(value, (int, float)) and float(value) > 20000:
        return datetime(1899, 12, 30, tzinfo=timezone.utc) + timedelta(days=float(value))
    raw = str(value).strip()
    if not raw:
        return None
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
    try:
        return _ensure_aware(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError:
        return None


def _same_day(value: Any, as_of: datetime) -> bool:
    parsed = _parse_datetime(value)
    return bool(parsed and parsed.date() == as_of.date())


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return round(float(value), 4)
    try:
        return round(float(str(value).strip().replace("%", "")), 4)
    except ValueError:
        return None


def _int(value: Any) -> int:
    number = _number(value)
    return int(number or 0)


def _boolish(value: Any) -> bool:
    normalized = _normalize_header(_text(value))
    return normalized in {"yes", "y", "true", "1", "used", "mapped"}


def _mean(values: list[float] | None) -> float:
    values = values or []
    return round(sum(values) / len(values), 2) if values else 0.0


def _max_or_zero(values: list[float] | None) -> float:
    values = values or []
    return round(max(values), 2) if values else 0.0
