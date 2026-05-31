"""Read-only May 23 unified route/LH scorecard projection."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
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
SCORECARD_PATH_ENV = "FLEETPULSE_UNIFIED_ROUTE_LH_SCORECARD_PATH"

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

    @classmethod
    def from_env(cls) -> "UnifiedRouteLHScorecardConfig":
        configured = os.getenv(SCORECARD_PATH_ENV, "").strip()
        if not configured:
            return cls(workbook_path=DEFAULT_SCORECARD_PATH)
        workbook_path = Path(configured).expanduser()
        if not workbook_path.is_absolute():
            workbook_path = REPO_ROOT / workbook_path
        return cls(workbook_path=workbook_path)


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
        definition_rows = read_xlsx_sheet_rows(workbook_path, "Metric Definitions")

        summary = _dashboard_summary(dashboard_rows)
        items = _scorecard_items(scorecard_rows)
        _add_computed_totals(summary, items)
        return {
            "generated_at": _now_iso(),
            "period_end": _period_end(workbook_path),
            "projection_mode": "read_only",
            "feed_status": "healthy",
            "feed_message": "Loaded unified route/LH scorecard workbook as a read-only planning artifact.",
            "source_authority": "K1 Group LLC / Xcelerator ReviewOrders export",
            "source_file": workbook_path.name,
            "required_config": [SCORECARD_PATH_ENV],
            "summary": summary,
            "items": items,
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
        "required_config": [SCORECARD_PATH_ENV],
        "summary": _base_summary(),
        "items": [],
        "action_summary": [],
        "source_notes": [],
        "source_boundaries": _source_boundaries(),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
