"""Read-only May 23 unified route/LH scorecard projection."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import os
from pathlib import Path
import re
from typing import Any

from utils.xlsx_reader import read_xlsx_sheet_rows


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCORECARD_PATH = (
    REPO_ROOT
    / "outputs"
    / "lane-stability-2026-05-23"
    / "K1_Unified_Route_LH_Scorecard_WE_2026-05-23.xlsx"
)
DEFAULT_CAPACITY_PLAN_PATH = (
    REPO_ROOT
    / "outputs"
    / "lane-stability-2026-05-23"
    / "K1_Sales_Capacity_Plan_WE_2026-05-23.xlsx"
)
SCORECARD_PATH_ENV = "FLEETPULSE_UNIFIED_ROUTE_LH_SCORECARD_PATH"
CAPACITY_PLAN_PATH_ENV = "FLEETPULSE_SALES_CAPACITY_PLAN_PATH"
CAPACITY_TIMELINE_HOURS = 12.0
MIN_ACTIONABLE_GAP_MINUTES = 60

WORK_TYPES = {"Local Route", "LH Lane"}
METRIC_KEYS = {
    "Scorecard Units": "scorecard_units",
    "Local Routes": "local_routes",
    "LH Lanes": "lh_lanes",
    "Company Avg Revenue/Hr": "company_avg_revenue_per_hour",
    "Missed Hours": "missed_hours",
    "Missed Hour Revenue": "missed_hour_revenue",
    "Avg Stability": "avg_stability_pct",
    "Avg On-Time": "avg_on_time_pct",
    "Avg Tech": "avg_tech_pct",
    "Safety": "safety_status",
}


@dataclass(frozen=True)
class UnifiedRouteLHScorecardConfig:
    """Runtime config for the read-only unified route/LH workbook."""

    workbook_path: Path = DEFAULT_SCORECARD_PATH
    capacity_plan_path: Path = DEFAULT_CAPACITY_PLAN_PATH

    @classmethod
    def from_env(cls) -> "UnifiedRouteLHScorecardConfig":
        return cls(
            workbook_path=_configured_path(SCORECARD_PATH_ENV, DEFAULT_SCORECARD_PATH),
            capacity_plan_path=_configured_path(CAPACITY_PLAN_PATH_ENV, DEFAULT_CAPACITY_PLAN_PATH),
        )


def get_unified_route_lh_scorecard(
    config: UnifiedRouteLHScorecardConfig | None = None,
) -> dict[str, Any]:
    """Return the local unified route/LH scorecard as a read-only app payload."""

    config = config or UnifiedRouteLHScorecardConfig.from_env()
    workbook_path = config.workbook_path
    if not workbook_path.exists():
        return _empty_payload(
            workbook_path,
            "awaiting_feed",
            f"Unified route/LH scorecard workbook not found. Configure {SCORECARD_PATH_ENV}.",
        )

    try:
        dashboard_rows = read_xlsx_sheet_rows(workbook_path, "Dashboard")
        scorecard_rows = read_xlsx_sheet_rows(workbook_path, "Unified Scorecard")
        capacity_plan_rows = _read_optional_sheet(config.capacity_plan_path, "Capacity Plan")
        gap_rows = _read_optional_sheet(workbook_path, "Gap Detail")
        definition_rows = read_xlsx_sheet_rows(workbook_path, "Metric Definitions")

        summary = _dashboard_summary(dashboard_rows)
        items = _scorecard_items(scorecard_rows)
        capacity_windows = _capacity_plan_windows(capacity_plan_rows, config.capacity_plan_path.name)
        if not capacity_windows:
            capacity_windows = _gap_detail_windows(gap_rows, workbook_path.name)
        _add_computed_totals(summary, items)
        _add_capacity_totals(summary, capacity_windows)
        return {
            "generated_at": _now_iso(),
            "period_end": _period_end(workbook_path),
            "projection_mode": "read_only",
            "feed_status": "healthy",
            "feed_message": "Loaded unified route/LH scorecard workbook as a read-only planning artifact.",
            "source_authority": "K1 Group LLC / Xcelerator ReviewOrders export",
            "source_file": workbook_path.name,
            "required_config": [SCORECARD_PATH_ENV, CAPACITY_PLAN_PATH_ENV],
            "summary": summary,
            "items": items,
            "capacity_windows": capacity_windows,
            "action_summary": _action_summary(items),
            "source_notes": _source_notes(definition_rows),
            "source_boundaries": _source_boundaries(),
        }
    except Exception as exc:
        return _empty_payload(workbook_path, "unavailable", f"{type(exc).__name__}: {exc}")


def _empty_payload(workbook_path: Path, feed_status: str, message: str) -> dict[str, Any]:
    return {
        "generated_at": _now_iso(),
        "period_end": _period_end(workbook_path),
        "projection_mode": "read_only",
        "feed_status": feed_status,
        "feed_message": message,
        "source_authority": "K1 Group LLC / Xcelerator ReviewOrders export",
        "source_file": workbook_path.name,
        "required_config": [SCORECARD_PATH_ENV, CAPACITY_PLAN_PATH_ENV],
        "summary": _base_summary(),
        "items": [],
        "capacity_windows": [],
        "action_summary": [],
        "source_notes": [],
        "source_boundaries": _source_boundaries(),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _configured_path(env_name: str, default_path: Path) -> Path:
    configured = os.getenv(env_name, "").strip()
    if not configured:
        return default_path
    path = Path(configured).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def _period_end(path: Path) -> str:
    match = re.search(r"WE_(\d{4}-\d{2}-\d{2})", path.name)
    return match.group(1) if match else ""


def _base_summary() -> dict[str, Any]:
    return {
        "scorecard_units": 0,
        "local_routes": 0,
        "lh_lanes": 0,
        "company_avg_revenue_per_hour": 0.0,
        "missed_hours": 0.0,
        "missed_hour_revenue": 0.0,
        "local_missed_hour_revenue": 0.0,
        "lh_missed_hour_revenue": 0.0,
        "capacity_window_count": 0,
        "actionable_gap_count": 0,
        "actionable_gap_hours": 0.0,
        "capacity_timeline_hours": CAPACITY_TIMELINE_HOURS,
        "capacity_gap_threshold_minutes": MIN_ACTIONABLE_GAP_MINUTES,
        "avg_stability_pct": None,
        "avg_on_time_pct": None,
        "avg_tech_pct": None,
        "safety_status": "Needs Geotab",
        "attendance_status": "Not scored",
    }


def _dashboard_summary(rows: list[list[str]]) -> dict[str, Any]:
    summary = _base_summary()
    for index, row in enumerate(rows[:-1]):
        next_row = rows[index + 1]
        for col_index, label in enumerate(row):
            key = METRIC_KEYS.get(label.strip())
            if not key:
                continue
            raw_value = next_row[col_index] if col_index < len(next_row) else ""
            if key.endswith("_status"):
                summary[key] = raw_value or summary[key]
            else:
                summary[key] = _number(raw_value) or 0.0
    return summary


def _read_optional_sheet(workbook_path: Path, sheet_name: str) -> list[list[str]]:
    if not workbook_path.exists():
        return []
    try:
        return read_xlsx_sheet_rows(workbook_path, sheet_name)
    except KeyError:
        return []


def _scorecard_items(rows: list[list[str]]) -> list[dict[str, Any]]:
    header_index = _header_index(rows)
    header = rows[header_index]
    items: list[dict[str, Any]] = []
    for row in rows[header_index + 1 :]:
        if not row or row[0] not in WORK_TYPES:
            continue
        record = {header[index]: row[index] if index < len(row) else "" for index in range(len(header))}
        items.append(_normalize_item(record))
    return sorted(items, key=lambda item: (-item["missed_hour_revenue"], item["work_type"], item["route_lh"]))


def _header_index(rows: list[list[str]]) -> int:
    for index, row in enumerate(rows):
        if row and row[0] == "Work Type":
            return index
    raise ValueError("Unified Scorecard header row not found")


def _normalize_item(record: dict[str, str]) -> dict[str, Any]:
    return {
        "work_type": record.get("Work Type", ""),
        "entity": record.get("Entity", ""),
        "route_lh": record.get("Route/LH", ""),
        "service": record.get("Service", ""),
        "customer_relationship": record.get("Customer / Relationship", ""),
        "primary_driver": record.get("Primary Driver", ""),
        "active_days": _number(record.get("Active Days")) or 0.0,
        "orders_or_stops": _number(record.get("Orders / Stops")) or 0.0,
        "current_sales": _money(record.get("Current Sales")),
        "avg_sales_per_day": _money(record.get("Avg Sales/Day")),
        "missed_hours": _number(record.get("Missed Hours")) or 0.0,
        "company_avg_revenue_per_hour": _money(record.get("Company Avg Revenue/Hr")),
        "missed_hour_revenue": _money(record.get("Missed Hour Revenue")),
        "stability_pct": _number(record.get("Stability %")),
        "on_time_pct": _number(record.get("On-Time Performance %")),
        "safety_pct": _number(record.get("Safety %")),
        "safety_data_status": record.get("Safety Data Status") or record.get("Safety %") or "Not scored",
        "tech_pct": _number(record.get("Tech Performance %")),
        "tech_data_status": record.get("Tech Data Status", ""),
        "attendance_pct": _number(record.get("Attendance %")),
        "attendance_data_status": record.get("Attendance Data Status") or record.get("Attendance %") or "Not scored",
        "driver_coverage_pct": _number(record.get("Driver Coverage %")),
        "gross_margin_pct": _number(record.get("Route/LH Gross Margin %")),
        "margin_target_pct": _number(record.get("Margin Target %")),
        "margin_status": record.get("Margin Status", ""),
        "relationship_score_pct": _number(record.get("Relationship Score %")),
        "relationship_band": record.get("Relationship Band", ""),
        "risk_management_band": record.get("Risk Management Band", ""),
        "sales_relationship_action": record.get("Sales / Relationship Action", ""),
        "capacity_status": record.get("Capacity Status", ""),
        "source_boundary": record.get("Source Boundary", ""),
    }


def _capacity_plan_windows(rows: list[list[str]], source_file: str) -> list[dict[str, Any]]:
    if not rows:
        return []

    header_index = _header_index_for(rows, "Date")
    header = rows[header_index]
    windows: list[dict[str, Any]] = []
    for row in rows[header_index + 1 :]:
        if len(row) < 4 or not row[0]:
            continue
        record = {header[index]: row[index] if index < len(row) else "" for index in range(len(header))}
        gap_hours = _number(record.get("Gap Hours")) or 0.0
        if gap_hours <= (MIN_ACTIONABLE_GAP_MINUTES / 60):
            continue

        date_text = record.get("Date", "")
        shift_range = _parse_time_range(record.get("Shift Window", ""), date_text)
        shift_start = shift_range[0] if shift_range else None
        gap_ranges = _parse_window_ranges(record.get("Capacity Gaps", ""), date_text, shift_start)
        active_ranges = _parse_window_ranges(record.get("Active Stop Windows", ""), date_text, shift_start)
        timeline_start = shift_start or _earliest_range_start(gap_ranges + active_ranges)
        timeline_end = (timeline_start + timedelta(hours=CAPACITY_TIMELINE_HOURS)) if timeline_start else None

        gaps = _capacity_gap_segments(record, gap_ranges, timeline_start, gap_hours)
        if not gaps:
            gaps = [_fallback_gap_segment(record, gap_hours)]

        active_segments = _capacity_segments(active_ranges, timeline_start, "active_stop")
        windows.append(
            {
                "entity": record.get("Entity", ""),
                "route_lh": record.get("Route", ""),
                "date": date_text,
                "primary_driver": record.get("Primary Driver", ""),
                "shift_window": record.get("Shift Window", ""),
                "active_stop_windows": record.get("Active Stop Windows", ""),
                "capacity_gaps": record.get("Capacity Gaps", ""),
                "gap_count": len(gaps),
                "actionable_gap_hours": round(gap_hours, 2),
                "display_gap_hours": round(
                    sum(float(segment["display_gap_hours"]) for segment in gaps), 2
                ),
                "suggested_added_stops": _number(record.get("Suggested Added Stops")) or 0.0,
                "timeline_start": _iso_or_blank(timeline_start),
                "timeline_end": _iso_or_blank(timeline_end),
                "timeline_hours": CAPACITY_TIMELINE_HOURS,
                "paid_window_basis": record.get("Paid Window Basis", ""),
                "source_file": source_file,
                "source_sheet": "Capacity Plan",
                "active_segments": active_segments,
                "gaps": gaps,
                "injection_guidance": record.get("Sales Move", "")
                or _capacity_guidance(record.get("Gap Type", ""), gap_hours),
                "source_boundary": (
                    "Approved capacity-plan workbook; FleetPulse displays working/gap windows only, "
                    "does not calculate injected revenue, and does not write dispatch changes."
                ),
            }
        )
    return _sort_capacity_windows(windows)


def _gap_detail_windows(rows: list[list[str]], source_file: str) -> list[dict[str, Any]]:
    if not rows:
        return []

    header_index = _header_index_for(rows, "Entity")
    header = rows[header_index]
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows[header_index + 1 :]:
        if len(row) < 4 or not row[0]:
            continue
        record = {header[index]: row[index] if index < len(row) else "" for index in range(len(header))}
        missed_hours = _number(record.get("Missed Hours")) or 0.0
        if missed_hours <= (MIN_ACTIONABLE_GAP_MINUTES / 60):
            continue

        gap_start = _excel_datetime(record.get("Gap From"))
        gap_end = _excel_datetime(record.get("Gap To"))
        grouped[
            (
                record.get("Entity", ""),
                record.get("Route") or record.get("Route/LH") or "",
                record.get("Date", ""),
                record.get("Paid Window Basis", ""),
            )
        ].append(
            {
                "record": record,
                "gap_start": gap_start,
                "gap_end": gap_end,
                "gap_type": record.get("Gap Type", ""),
                "gap_window": record.get("Gap Window", ""),
                "gap_hours": missed_hours,
            }
        )

    windows: list[dict[str, Any]] = []
    for (entity, route_lh, date_text, paid_window_basis), records in grouped.items():
        timeline_start = _earliest_range_start(
            [(record["gap_start"], record["gap_end"]) for record in records if record["gap_start"]]
        )
        timeline_end = (timeline_start + timedelta(hours=CAPACITY_TIMELINE_HOURS)) if timeline_start else None
        gaps: list[dict[str, Any]] = []
        for record in records:
            gap_start = record["gap_start"]
            gap_end = record["gap_end"]
            gap_start_minute, gap_end_minute = _segment_minutes(gap_start, gap_end, timeline_start)
            if gap_end_minute <= gap_start_minute:
                gap_start_minute = 0.0
                gap_end_minute = min(record["gap_hours"] * 60, CAPACITY_TIMELINE_HOURS * 60)
            display_gap_hours = round(max(gap_end_minute - gap_start_minute, 0.0) / 60, 2)
            gaps.append(
                {
                    "gap_type": record["gap_type"],
                    "gap_window": record["gap_window"],
                    "gap_hours": round(record["gap_hours"], 2),
                    "display_gap_hours": display_gap_hours,
                    "gap_start_minute": round(gap_start_minute, 2),
                    "gap_end_minute": round(gap_end_minute, 2),
                    "injection_guidance": _capacity_guidance(record["gap_type"], record["gap_hours"]),
                }
            )

        windows.append(
            {
                "entity": entity,
                "route_lh": route_lh,
                "date": date_text,
                "primary_driver": "",
                "shift_window": "",
                "active_stop_windows": "",
                "capacity_gaps": "; ".join(gap["gap_window"] for gap in gaps if gap["gap_window"]),
                "gap_count": len(gaps),
                "actionable_gap_hours": round(sum(record["gap_hours"] for record in records), 2),
                "display_gap_hours": round(
                    sum(float(segment["display_gap_hours"]) for segment in gaps), 2
                ),
                "suggested_added_stops": 0.0,
                "timeline_start": _iso_or_blank(timeline_start),
                "timeline_end": _iso_or_blank(timeline_end),
                "timeline_hours": CAPACITY_TIMELINE_HOURS,
                "paid_window_basis": paid_window_basis,
                "source_file": source_file,
                "source_sheet": "Gap Detail",
                "active_segments": [],
                "gaps": gaps,
                "injection_guidance": "Review source gap windows before adding compatible work.",
                "source_boundary": (
                    "Xcelerator ReviewOrders gap detail; FleetPulse marks capacity only, "
                    "does not calculate injected revenue, and does not write dispatch changes."
                ),
            }
        )
    return _sort_capacity_windows(windows)


def _sort_capacity_windows(windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        windows,
        key=lambda item: (-float(item["actionable_gap_hours"]), item["route_lh"], item["date"]),
    )


def _header_index_for(rows: list[list[str]], first_column: str) -> int:
    for index, row in enumerate(rows):
        if row and row[0] == first_column:
            return index
    raise ValueError(f"{first_column} header row not found")


def _excel_datetime(value: Any) -> datetime | None:
    numeric = _number(value)
    if numeric is None:
        return None
    day = date(1899, 12, 30) + timedelta(days=int(numeric))
    fraction = numeric - int(numeric)
    seconds = round(fraction * 24 * 60 * 60)
    return datetime.combine(day, time.min) + timedelta(seconds=seconds)


def _parse_window_ranges(
    value: str,
    date_text: str,
    anchor_start: datetime | None = None,
) -> list[tuple[datetime, datetime]]:
    return [
        parsed
        for part in str(value or "").split(";")
        if (parsed := _parse_time_range(part.strip(), date_text, anchor_start)) is not None
    ]


def _parse_time_range(
    value: str,
    date_text: str,
    anchor_start: datetime | None = None,
) -> tuple[datetime, datetime] | None:
    if not value or not date_text:
        return None
    try:
        base_date = datetime.fromisoformat(date_text).date()
    except ValueError:
        return None
    matches = re.findall(r"(\d{1,2}:\d{2})\s*([AP]M)", value, flags=re.IGNORECASE)
    if len(matches) < 2:
        return None
    start = _combine_time(base_date, matches[0])
    end = _combine_time(base_date, matches[1])
    if end <= start:
        end += timedelta(days=1)
    if anchor_start and end <= anchor_start:
        start += timedelta(days=1)
        end += timedelta(days=1)
    return start, end


def _combine_time(base_date: date, match: tuple[str, str]) -> datetime:
    clock, meridiem = match
    parsed = datetime.strptime(f"{clock} {meridiem.upper()}", "%I:%M %p")
    return datetime.combine(base_date, parsed.time())


def _earliest_range_start(ranges: list[tuple[datetime | None, datetime | None]]) -> datetime | None:
    starts = [start for start, _end in ranges if start is not None]
    return min(starts) if starts else None


def _capacity_gap_segments(
    record: dict[str, str],
    gap_ranges: list[tuple[datetime, datetime]],
    timeline_start: datetime | None,
    fallback_gap_hours: float,
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    source_gap_hours = fallback_gap_hours / len(gap_ranges) if gap_ranges else fallback_gap_hours
    for gap_start, gap_end in gap_ranges:
        gap_start_minute, gap_end_minute = _segment_minutes(gap_start, gap_end, timeline_start)
        if gap_end_minute <= gap_start_minute:
            continue
        display_gap_hours = round((gap_end_minute - gap_start_minute) / 60, 2)
        segments.append(
            {
                "gap_type": record.get("Gap Type", "") or "Capacity gap",
                "gap_window": _display_time_range(gap_start, gap_end),
                "gap_hours": round(source_gap_hours, 2),
                "display_gap_hours": display_gap_hours,
                "gap_start_minute": round(gap_start_minute, 2),
                "gap_end_minute": round(gap_end_minute, 2),
                "injection_guidance": _capacity_guidance(record.get("Gap Type", ""), source_gap_hours),
            }
        )
    return segments


def _fallback_gap_segment(record: dict[str, str], gap_hours: float) -> dict[str, Any]:
    gap_end_minute = min(gap_hours * 60, CAPACITY_TIMELINE_HOURS * 60)
    return {
        "gap_type": record.get("Gap Type", "") or "Capacity gap",
        "gap_window": record.get("Capacity Gaps", "") or record.get("Gap Window", ""),
        "gap_hours": round(gap_hours, 2),
        "display_gap_hours": round(gap_end_minute / 60, 2),
        "gap_start_minute": 0.0,
        "gap_end_minute": round(gap_end_minute, 2),
        "injection_guidance": _capacity_guidance(record.get("Gap Type", ""), gap_hours),
    }


def _capacity_segments(
    ranges: list[tuple[datetime, datetime]],
    timeline_start: datetime | None,
    segment_type: str,
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for start, end in ranges:
        start_minute, end_minute = _segment_minutes(start, end, timeline_start)
        if end_minute <= start_minute:
            continue
        segments.append(
            {
                "type": segment_type,
                "label": _display_time_range(start, end),
                "start_minute": round(start_minute, 2),
                "end_minute": round(end_minute, 2),
                "hours": round((end_minute - start_minute) / 60, 2),
            }
        )
    return segments


def _segment_minutes(
    start: datetime | None,
    end: datetime | None,
    timeline_start: datetime | None,
) -> tuple[float, float]:
    if not start or not end or not timeline_start:
        return 0.0, 0.0
    timeline_minutes = CAPACITY_TIMELINE_HOURS * 60
    start_minute = max((start - timeline_start).total_seconds() / 60, 0.0)
    end_minute = min((end - timeline_start).total_seconds() / 60, timeline_minutes)
    return start_minute, max(end_minute, 0.0)


def _display_time_range(start: datetime, end: datetime) -> str:
    return f"{_display_time(start)} - {_display_time(end)}"


def _display_time(value: datetime) -> str:
    return value.strftime("%I:%M %p").lstrip("0")


def _iso_or_blank(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _capacity_guidance(gap_type: str, missed_hours: float) -> str:
    gap_type_text = gap_type.strip() or "Capacity gap"
    if missed_hours >= CAPACITY_TIMELINE_HOURS:
        return f"{gap_type_text}: validate service fit before filling a full 12h planning window."
    if missed_hours >= 4:
        return f"{gap_type_text}: target compatible work inside this open route/LH window."
    return f"{gap_type_text}: use for short-fill work only if service constraints fit."


def _add_computed_totals(summary: dict[str, Any], items: list[dict[str, Any]]) -> None:
    if items:
        summary["scorecard_units"] = len(items)
        summary["local_routes"] = sum(1 for item in items if item["work_type"] == "Local Route")
        summary["lh_lanes"] = sum(1 for item in items if item["work_type"] == "LH Lane")
        summary["local_missed_hour_revenue"] = _round_money(
            sum(item["missed_hour_revenue"] for item in items if item["work_type"] == "Local Route")
        )
        summary["lh_missed_hour_revenue"] = _round_money(
            sum(item["missed_hour_revenue"] for item in items if item["work_type"] == "LH Lane")
        )
        summary["missed_hour_revenue"] = _round_money(
            summary["local_missed_hour_revenue"] + summary["lh_missed_hour_revenue"]
        )
        summary["missed_hours"] = round(sum(item["missed_hours"] for item in items), 2)


def _add_capacity_totals(summary: dict[str, Any], windows: list[dict[str, Any]]) -> None:
    summary["capacity_window_count"] = len(windows)
    summary["actionable_gap_count"] = sum(int(item["gap_count"]) for item in windows)
    summary["actionable_gap_hours"] = round(sum(float(item["actionable_gap_hours"]) for item in windows), 2)


def _action_summary(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"action": "", "units": 0, "missed_hours": 0.0, "missed_hour_revenue": 0.0}
    )
    for item in items:
        action = item["sales_relationship_action"] or "No action guidance"
        bucket = buckets[action]
        bucket["action"] = action
        bucket["units"] += 1
        bucket["missed_hours"] += item["missed_hours"]
        bucket["missed_hour_revenue"] += item["missed_hour_revenue"]

    rows = []
    for bucket in buckets.values():
        rows.append(
            {
                "action": bucket["action"],
                "units": bucket["units"],
                "missed_hours": round(bucket["missed_hours"], 2),
                "missed_hour_revenue": _round_money(bucket["missed_hour_revenue"]),
            }
        )
    return sorted(rows, key=lambda row: (-row["missed_hour_revenue"], row["action"]))


def _source_notes(rows: list[list[str]]) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    for row in rows:
        if len(row) >= 2 and row[0] not in {"", "Metric", "Metric Definitions"}:
            notes.append({"metric": row[0], "definition": row[1]})
    return notes


def _source_boundaries() -> list[dict[str, Any]]:
    return [
        {
            "system": "Xcelerator",
            "entity": "K1 Group LLC",
            "authority": ["revenue", "driver pay", "expenses", "load lifecycle", "dispatch operations"],
            "rule": "Operations and financial values remain authoritative in Xcelerator; FleetPulse only renders the exported scorecard.",
        },
        {
            "system": "Geotab",
            "entity": "K1 Logistics Inc",
            "authority": ["vehicle telemetry", "engine diagnostics", "maintenance", "safety"],
            "rule": "Safety stays Not scored unless live Geotab rows are available; workbook rows are not converted to safety facts.",
        },
        {
            "system": "FleetPulse",
            "entity": "Read-side projection",
            "authority": [],
            "rule": "This endpoint has no write path and does not update Xcelerator, Geotab, SharePoint, Power BI, or Teams.",
        },
    ]


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip().replace("$", "").replace(",", "")
    if not raw or raw.casefold() in {"not scored", "needs geotab", "missing"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _money(value: Any) -> float:
    return _round_money(_number(value) or 0.0)


def _round_money(value: float) -> float:
    return round(float(value), 2)
