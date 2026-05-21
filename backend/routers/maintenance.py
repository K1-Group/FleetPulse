"""Predictive maintenance endpoints – optimized with caching and timeouts."""

import json
import logging
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, List

from fastapi import APIRouter, HTTPException, Query

from _cache import get_cached, set_cached
from geotab_client import GeotabClient
from models import (
    MaintenancePrediction,
    VehicleMaintenanceDetail,
    MaintenanceCost,
    UrgentMaintenanceAlert,
    UrgencyLevel,
)

logger = logging.getLogger(__name__)
router = APIRouter()

DEFAULT_MAINTENANCE_INTERVALS = {
    "oil_change": {"miles": 5000, "months": 6},
    "brake_service": {"miles": 30000, "months": 24},
    "tire_rotation": {"miles": 7500, "months": 12},
    "transmission_service": {"miles": 60000, "months": 48},
}

DEFAULT_MAINTENANCE_COSTS = {
    "oil_change": 75,
    "brake_service": 600,
    "tire_rotation": 25,
    "transmission_service": 300,
    "tires_replacement": 600,
}

DEFAULT_FAULT_LOOKBACK_DAYS = 30
GEOTAB_MAINTENANCE_AUTHORITY = "K1 Logistics Inc / Geotab diagnostics"

DEFAULT_CRITICAL_FAULT_TERMS = (
    "aftertreatment",
    "brake",
    "coolant",
    "derate",
    "dpf",
    "emission",
    "engine oil pressure",
    "moderately severe",
    "overheat",
    "severe",
    "shutdown",
    "transmission",
)

DEFAULT_HIGH_FAULT_TERMS = (
    "abnormal update rate",
    "battery",
    "condition exists",
    "data erratic",
    "fuel pressure",
    "j1939",
    "low voltage",
    "oil",
    "out of calibration",
    "pressure",
    "warning light",
)

DEFAULT_RISK_THRESHOLDS = {
    "critical": 85,
    "high": 70,
    "medium": 50,
}

DEFAULT_SCORING_CONFIG = {
    "base_score": 25,
    "fault_count_weight": 2,
    "fault_count_cap": 20,
    "active_fault_weight": 3,
    "active_fault_cap": 18,
    "recurring_code_weight": 8,
    "recurring_code_cap": 16,
    "persistent_cycle_weight": 3,
    "persistent_cycle_cap": 12,
    "critical_severity_bonus": 30,
    "high_severity_bonus": 18,
    "medium_severity_bonus": 10,
    "recent_seen_days": 3,
    "recent_seen_bonus": 8,
    "confidence_base": 0.42,
    "confidence_fault_count_cap": 12,
    "confidence_fault_weight": 0.025,
    "confidence_recurring_bonus": 0.14,
    "confidence_active_bonus": 0.12,
    "confidence_recent_seen_days": 7,
    "confidence_recent_bonus": 0.08,
    "confidence_cap": 0.96,
}


def _env_int(name: str, default: int, *, min_value: int | None = None, max_value: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid integer value for %s; using default", name)
        return default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def _env_float(name: str, default: float, *, min_value: float | None = None, max_value: float | None = None) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Invalid numeric value for %s; using default", name)
        return default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def _env_json_object(name: str, default: dict[str, Any]) -> dict[str, Any]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return dict(default)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON value for %s; using default", name)
        return dict(default)
    if not isinstance(parsed, dict):
        logger.warning("JSON value for %s must be an object; using default", name)
        return dict(default)
    return parsed


def _float_from_mapping(value: Any, default: float, *, min_value: float = 0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, parsed)


def _maintenance_intervals() -> dict[str, dict[str, float]]:
    configured = _env_json_object("FLEETPULSE_MAINTENANCE_INTERVALS_JSON", DEFAULT_MAINTENANCE_INTERVALS)
    intervals: dict[str, dict[str, float]] = {}
    for service_type, raw in configured.items():
        if not isinstance(raw, dict):
            continue
        default = DEFAULT_MAINTENANCE_INTERVALS.get(service_type, {"miles": 0, "months": 0})
        miles = _float_from_mapping(raw.get("miles"), float(default.get("miles", 0)), min_value=0)
        months = _float_from_mapping(raw.get("months"), float(default.get("months", 0)), min_value=0)
        if miles > 0 or months > 0:
            intervals[service_type] = {"miles": miles, "months": months}
    return intervals or dict(DEFAULT_MAINTENANCE_INTERVALS)


def _maintenance_costs() -> dict[str, float]:
    configured = _env_json_object("FLEETPULSE_MAINTENANCE_COSTS_JSON", DEFAULT_MAINTENANCE_COSTS)
    costs: dict[str, float] = {}
    for service_type, default_cost in DEFAULT_MAINTENANCE_COSTS.items():
        costs[service_type] = _float_from_mapping(configured.get(service_type), float(default_cost), min_value=0)
    for service_type, raw_cost in configured.items():
        if service_type in costs:
            continue
        costs[service_type] = _float_from_mapping(raw_cost, 0, min_value=0)
    return costs


def _fault_lookback_days() -> int:
    return _env_int("FLEETPULSE_MAINTENANCE_FAULT_LOOKBACK_DAYS", DEFAULT_FAULT_LOOKBACK_DAYS, min_value=1, max_value=90)


def _avg_miles_per_day() -> float:
    return _env_float("FLEETPULSE_MAINTENANCE_AVG_MILES_PER_DAY", 50, min_value=1, max_value=1000)


def _days_per_month() -> float:
    return _env_float("FLEETPULSE_MAINTENANCE_DAYS_PER_MONTH", 30, min_value=27, max_value=31)


def _service_baseline_days() -> int:
    return _env_int("FLEETPULSE_MAINTENANCE_SERVICE_BASELINE_DAYS", 90, min_value=0, max_value=3650)


def _service_baseline_miles() -> float:
    return _env_float("FLEETPULSE_MAINTENANCE_SERVICE_BASELINE_MILES", 3000, min_value=0, max_value=500000)


def _forecast_primary_days() -> int:
    return _env_int("FLEETPULSE_MAINTENANCE_FORECAST_PRIMARY_DAYS", 30, min_value=1, max_value=365)


def _forecast_secondary_days() -> int:
    return _env_int("FLEETPULSE_MAINTENANCE_FORECAST_SECONDARY_DAYS", 90, min_value=1, max_value=730)


def _unknown_fault_high_count() -> int:
    return _env_int("FLEETPULSE_MAINTENANCE_UNKNOWN_FAULT_HIGH_COUNT", 25, min_value=1, max_value=1000)


def _env_terms(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    terms = tuple(term.strip().lower() for term in raw.split(",") if term.strip())
    return terms or default


def _critical_fault_terms() -> tuple[str, ...]:
    return _env_terms("FLEETPULSE_MAINTENANCE_CRITICAL_FAULT_TERMS", DEFAULT_CRITICAL_FAULT_TERMS)


def _high_fault_terms() -> tuple[str, ...]:
    return _env_terms("FLEETPULSE_MAINTENANCE_HIGH_FAULT_TERMS", DEFAULT_HIGH_FAULT_TERMS)


def _risk_thresholds() -> dict[str, int]:
    configured = _env_json_object("FLEETPULSE_MAINTENANCE_RISK_THRESHOLDS_JSON", DEFAULT_RISK_THRESHOLDS)
    thresholds: dict[str, int] = {}
    for key, default in DEFAULT_RISK_THRESHOLDS.items():
        thresholds[key] = int(_float_from_mapping(configured.get(key), float(default), min_value=0))
        thresholds[key] = min(thresholds[key], 100)
    if not (0 <= thresholds["medium"] <= thresholds["high"] <= thresholds["critical"] <= 100):
        logger.warning("Invalid maintenance risk threshold ordering; using defaults")
        return dict(DEFAULT_RISK_THRESHOLDS)
    return thresholds


def _scoring_config() -> dict[str, float]:
    configured = _env_json_object("FLEETPULSE_MAINTENANCE_SCORING_JSON", DEFAULT_SCORING_CONFIG)
    return {
        key: _float_from_mapping(configured.get(key), float(default), min_value=0)
        for key, default in DEFAULT_SCORING_CONFIG.items()
    }


def _maintenance_runtime_config() -> dict[str, Any]:
    return {
        "fault_lookback_days": _fault_lookback_days(),
        "service_baseline_days": _service_baseline_days(),
        "service_baseline_miles": _service_baseline_miles(),
        "avg_miles_per_day": _avg_miles_per_day(),
        "forecast_primary_days": _forecast_primary_days(),
        "forecast_secondary_days": _forecast_secondary_days(),
        "unknown_fault_high_count": _unknown_fault_high_count(),
        "risk_thresholds": _risk_thresholds(),
        "interval_service_count": len(_maintenance_intervals()),
        "cost_service_count": len(_maintenance_costs()),
        "config_source": "environment_overrides_or_defaults",
    }


def _as_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _fault_value(fault: dict, *keys: str) -> Any:
    diagnostic = fault.get("diagnostic") if isinstance(fault.get("diagnostic"), dict) else {}
    for key in keys:
        if key in fault and fault.get(key) not in (None, ""):
            return fault.get(key)
        if key in diagnostic and diagnostic.get(key) not in (None, ""):
            return diagnostic.get(key)
    return None


def _fault_code_value(fault: dict) -> str:
    value = _fault_value(
        fault,
        "fault_code",
        "FaultCode",
        "code",
        "id",
        "DiagnosticId",
        "diagnosticId",
    )
    code = _as_text(value, "Unknown")
    if code == "Unknown":
        name = _as_text(_fault_value(fault, "FaultCodeDescription", "name", "description"))
        if name:
            return name[:80]
    return code


def _fault_description(fault: dict) -> str:
    return _as_text(
        _fault_value(
            fault,
            "FaultCodeDescription",
            "description",
            "name",
            "FailureModeDescription",
            "DiagnosticName",
        ),
        "Unknown fault",
    )


def _description_is_unknown_fault(description: Any) -> bool:
    text = _as_text(description).lower()
    return text in {"unknown fault", "**unknown fault"} or "unknown diagnostic" in text


def _fault_is_unknown(fault: dict) -> bool:
    return _description_is_unknown_fault(_fault_description(fault))


def _fault_text(fault: dict) -> str:
    parts = [
        _fault_code_value(fault),
        _fault_description(fault),
        _as_text(_fault_value(fault, "FailureModeDescription")),
        _as_text(_fault_value(fault, "ControllerDescription")),
        _as_text(_fault_value(fault, "Component")),
        _as_text(_fault_value(fault, "DiagnosticType")),
    ]
    return " ".join(part for part in parts if part).lower()


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = _as_text(value)
    if not text:
        return None
    try:
        if len(text) == 10:
            return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _fault_seen_at(fault: dict) -> datetime | None:
    return _parse_datetime(
        _fault_value(
            fault,
            "dateTime",
            "date",
            "Local_Date",
            "AnyStatesDateTimeFirstSeen",
            "timestamp",
        )
    )


def _fault_vehicle_id(fault: dict) -> str:
    device = fault.get("device") if isinstance(fault.get("device"), dict) else {}
    return _as_text(
        fault.get("vehicle_id")
        or fault.get("source_vehicle_id")
        or fault.get("DeviceId")
        or device.get("id"),
        "unknown",
    )


def _fault_vehicle_name(fault: dict, fallback: str = "Unknown Vehicle") -> str:
    device = fault.get("device") if isinstance(fault.get("device"), dict) else {}
    return _as_text(
        fault.get("vehicle_name")
        or fault.get("VehicleName")
        or fault.get("Name")
        or device.get("name"),
        fallback,
    )


def _fault_is_active(fault: dict) -> bool:
    return not (_fault_value(fault, "dismissDateTime", "dismiss_date_time", "DismissDateTime"))


def _fault_component(text: str) -> str:
    if any(term in text for term in ("coolant", "thermostat", "temperature", "overheat")):
        return "Cooling"
    if "oil" in text:
        return "Engine lubrication"
    if any(term in text for term in ("aftertreatment", "dpf", "regen", "emission", "def")):
        return "Aftertreatment"
    if any(term in text for term in ("brake", "abs")):
        return "Brakes"
    if "transmission" in text:
        return "Transmission"
    if any(term in text for term in ("battery", "voltage", "alternator")):
        return "Electrical"
    if any(term in text for term in ("fuel", "intake", "manifold", "pressure")):
        return "Air/fuel"
    if any(term in text for term in ("j1939", "network", "source address", "abnormal update")):
        return "Network/communications"
    return "General powertrain"


def _fault_severity(fault: dict) -> str:
    text = _fault_text(fault)
    if any(term in text for term in _critical_fault_terms()):
        return "critical"
    if any(term in text for term in _high_fault_terms()):
        return "high"
    if "unknown diagnostic" in text:
        return "medium"
    return "low"


def _predicted_issue(component: str, top_description: str) -> str:
    if component == "Cooling":
        return "Cooling system failure risk"
    if component == "Engine lubrication":
        return "Oil service or lubrication risk"
    if component == "Aftertreatment":
        return "Aftertreatment derate risk"
    if component == "Brakes":
        return "Brake system service risk"
    if component == "Transmission":
        return "Transmission service risk"
    if component == "Electrical":
        return "Electrical charging or voltage risk"
    if component == "Air/fuel":
        return "Air/fuel pressure performance risk"
    if component == "Network/communications":
        return "Vehicle network communication risk"
    return top_description or "Maintenance risk detected"


def _decision_from_score(score: int) -> tuple[UrgencyLevel, str, str]:
    thresholds = _risk_thresholds()
    if score >= thresholds["critical"]:
        return (
            UrgencyLevel.CRITICAL,
            "hold_and_inspect_now",
            "Hold the asset for maintenance inspection before dispatch if operationally possible.",
        )
    if score >= thresholds["high"]:
        return (
            UrgencyLevel.HIGH,
            "schedule_repair_24h",
            "Schedule diagnosis or repair in the next 24 hours.",
        )
    if score >= thresholds["medium"]:
        return (
            UrgencyLevel.MEDIUM,
            "diagnose_next_service_window",
            "Add diagnosis to the next available service window.",
        )
    return (
        UrgencyLevel.LOW,
        "monitor",
        "Monitor trend and re-score on the next Geotab refresh.",
    )


def _build_execution_plan(urgency: UrgencyLevel, component: str, recurring_codes: list[str]) -> list[str]:
    plan = [
        "Review Geotab diagnostic history and last-seen timestamp.",
        f"Inspect {component.lower()} system evidence before clearing any code.",
    ]
    if recurring_codes:
        plan.append(f"Prioritize recurring code(s): {', '.join(recurring_codes[:4])}.")
    if urgency in {UrgencyLevel.CRITICAL, UrgencyLevel.HIGH}:
        plan.append("Assign maintenance owner and confirm repair outcome back to the FleetPulse maintenance evidence trail.")
    else:
        plan.append("Keep asset in watch status until the next diagnostic refresh.")
    return plan


def _fault_insights(faults: list[dict]) -> list[dict]:
    grouped: dict[str, dict[str, Any]] = {}
    for fault in faults:
        code = _fault_code_value(fault)
        description = _fault_description(fault)
        severity = _fault_severity(fault)
        component = _fault_component(_fault_text(fault))
        seen_at = _fault_seen_at(fault)
        item = grouped.setdefault(
            code,
            {
                "code": code,
                "description": description,
                "count": 0,
                "severity": severity,
                "component": component,
                "last_seen": seen_at,
            },
        )
        item["count"] += int(fault.get("count") or fault.get("Count") or 1)
        if seen_at and (item.get("last_seen") is None or seen_at > item["last_seen"]):
            item["last_seen"] = seen_at
        if severity == "critical" or item.get("severity") not in {"critical", "high"}:
            item["severity"] = severity
    return sorted(
        grouped.values(),
        key=lambda row: (
            {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(row["severity"], 0),
            row["count"],
        ),
        reverse=True,
    )


def _build_maintenance_decisions(faults: list[dict], days: int) -> list[dict]:
    by_vehicle: dict[str, list[dict]] = defaultdict(list)
    for fault in faults:
        by_vehicle[_fault_vehicle_id(fault)].append(fault)

    decisions: list[dict] = []
    now = datetime.now(timezone.utc)
    scoring = _scoring_config()
    for vehicle_id, vehicle_faults in by_vehicle.items():
        if not vehicle_faults:
            continue
        insights = _fault_insights(vehicle_faults)
        if not insights:
            continue
        code_counts = Counter(_fault_code_value(fault) for fault in vehicle_faults)
        recurring_codes = [code for code, count in code_counts.items() if count >= 2 and code != "Unknown"]
        active_count = sum(1 for fault in vehicle_faults if _fault_is_active(fault))
        persistent_count = sum(1 for fault in vehicle_faults if bool(fault.get("IsPersistentCycle")))
        latest_seen = max((_fault_seen_at(fault) for fault in vehicle_faults if _fault_seen_at(fault)), default=None)
        top = insights[0]
        component = top.get("component") or "General powertrain"

        score = scoring["base_score"]
        score += min(len(vehicle_faults) * scoring["fault_count_weight"], scoring["fault_count_cap"])
        score += min(active_count * scoring["active_fault_weight"], scoring["active_fault_cap"])
        score += min(len(recurring_codes) * scoring["recurring_code_weight"], scoring["recurring_code_cap"])
        score += min(persistent_count * scoring["persistent_cycle_weight"], scoring["persistent_cycle_cap"])
        if top["severity"] == "critical":
            score += scoring["critical_severity_bonus"]
        elif top["severity"] == "high":
            score += scoring["high_severity_bonus"]
        elif top["severity"] == "medium":
            score += scoring["medium_severity_bonus"]
        if latest_seen and (now - latest_seen) <= timedelta(days=scoring["recent_seen_days"]):
            score += scoring["recent_seen_bonus"]
        risk_score = int(max(0, min(round(score), 100)))
        urgency, decision, recommended_action = _decision_from_score(risk_score)
        confidence = min(
            scoring["confidence_cap"],
            scoring["confidence_base"]
            + min(len(vehicle_faults), scoring["confidence_fault_count_cap"]) * scoring["confidence_fault_weight"]
            + (scoring["confidence_recurring_bonus"] if recurring_codes else 0)
            + (scoring["confidence_active_bonus"] if active_count else 0)
            + (
                scoring["confidence_recent_bonus"]
                if latest_seen and (now - latest_seen) <= timedelta(days=scoring["confidence_recent_seen_days"])
                else 0
            ),
        )

        vehicle_name = _fault_vehicle_name(vehicle_faults[0], vehicle_id)
        evidence = [
            f"{len(vehicle_faults)} Geotab fault row(s) in the previous {days} days",
            f"{active_count} active/unresolved fault row(s)",
        ]
        if recurring_codes:
            evidence.append(f"Recurring code pattern: {', '.join(recurring_codes[:4])}")
        if latest_seen:
            evidence.append(f"Latest Geotab code seen {latest_seen.isoformat()}")

        decisions.append(
            {
                "vehicle_id": vehicle_id,
                "vehicle_name": vehicle_name,
                "decision": decision,
                "urgency": urgency,
                "risk_score": risk_score,
                "health_score": max(0, 100 - risk_score),
                "confidence": round(confidence, 2),
                "predicted_issue": _predicted_issue(component, top.get("description", "")),
                "recommended_action": recommended_action,
                "execution_plan": _build_execution_plan(urgency, component, recurring_codes),
                "evidence": evidence,
                "fault_insights": insights[:6],
                "source_authority": GEOTAB_MAINTENANCE_AUTHORITY,
                "automation_mode": "ai_recommends_human_executes",
            }
        )

    return sorted(
        decisions,
        key=lambda row: (row["risk_score"], row["confidence"], row["vehicle_name"]),
        reverse=True,
    )


def _fallback_fault_rows_from_geotab(faults_map: dict[str, list[dict]], devices: list[dict]) -> list[dict]:
    names = {device.get("id"): device.get("name", "Unknown Vehicle") for device in devices}
    rows: list[dict] = []
    for device_id, faults in faults_map.items():
        for fault in faults:
            row = dict(fault)
            row["vehicle_id"] = device_id
            row["vehicle_name"] = names.get(device_id, device_id)
            rows.append(row)
    return rows


def _fault_insight_is_unknown(item: dict[str, Any]) -> bool:
    return _description_is_unknown_fault(item.get("description"))


def _fault_code_summary(faults: list[dict], limit: int = 4) -> list[dict[str, Any]]:
    all_insights = _fault_insights(faults)
    unknown_count = sum(int(item.get("count") or 0) for item in all_insights if _fault_insight_is_unknown(item))
    unknown_examples = [
        _as_text(item.get("code"))
        for item in all_insights
        if _fault_insight_is_unknown(item) and _as_text(item.get("code"))
    ][:4]
    known_rows = [
        {
            "code": item["code"],
            "description": (
                f"{item['description']} (x{item['count']})"
                if item["count"] > 1
                else item["description"]
            ),
            "count": item["count"],
            "severity": item.get("severity", "low"),
        }
        for item in all_insights
        if not _fault_insight_is_unknown(item)
    ]
    display_limit = max(limit - 1, 1) if unknown_count else limit
    rows = known_rows[:display_limit]
    if unknown_count:
        examples = ", ".join(unknown_examples)
        rows.append(
            {
                "code": "unmapped",
                "description": (
                    f"{unknown_count} unmapped Geotab diagnostic row(s)"
                    + (f" · examples: {examples}" if examples else "")
                ),
                "count": unknown_count,
                "severity": "mapping_needed",
            }
        )
    return rows[:limit]


def _coerce_urgency(value: Any) -> UrgencyLevel | None:
    if isinstance(value, UrgencyLevel):
        return value
    try:
        return UrgencyLevel(str(value))
    except ValueError:
        return None


def _urgency_sort_value(urgency: UrgencyLevel) -> int:
    return {
        UrgencyLevel.CRITICAL: 0,
        UrgencyLevel.HIGH: 1,
        UrgencyLevel.MEDIUM: 2,
        UrgencyLevel.LOW: 3,
    }.get(urgency, 9)


def _fault_urgency_from_known_faults(faults: list[dict]) -> UrgencyLevel | None:
    severities = {_fault_severity(fault) for fault in faults}
    if "critical" in severities:
        return UrgencyLevel.CRITICAL
    if "high" in severities:
        return UrgencyLevel.HIGH
    if "medium" in severities:
        return UrgencyLevel.MEDIUM
    if faults:
        return UrgencyLevel.LOW
    return None


def _get_devices_cached() -> list[dict]:
    cached = get_cached("maint:devices", ttl=300)
    if cached is not None:
        return cached
    try:
        devices = GeotabClient.get().get_devices()
        set_cached("maint:devices", devices)
        return devices
    except (TimeoutError, Exception) as e:
        logger.warning(f"Failed to fetch devices for maintenance: {e}")
        return []


def calculate_maintenance_due_date(last_service: datetime, odometer_at_service: float,
                                   current_odometer: float, service_type: str) -> tuple[datetime, bool]:
    intervals = _maintenance_intervals()[service_type]
    miles_since_service = current_odometer - odometer_at_service
    miles_remaining = intervals["miles"] - miles_since_service
    days_until_due = max(0, miles_remaining / _avg_miles_per_day())
    due_date_by_miles = datetime.now(timezone.utc) + timedelta(days=days_until_due)
    due_date_by_time = last_service + timedelta(days=intervals["months"] * _days_per_month())
    due_date = min(due_date_by_miles, due_date_by_time)
    is_overdue = due_date < datetime.now(timezone.utc)
    return due_date, is_overdue


def get_urgency_level(due_date: datetime, has_fault_codes: bool = False) -> UrgencyLevel:
    if has_fault_codes:
        return UrgencyLevel.CRITICAL
    days_until_due = (due_date - datetime.now(timezone.utc)).days
    if days_until_due < 0:
        return UrgencyLevel.CRITICAL
    elif days_until_due <= 7:
        return UrgencyLevel.HIGH
    elif days_until_due <= 30:
        return UrgencyLevel.MEDIUM
    return UrgencyLevel.LOW


def _get_fleet_odometers() -> dict[str, float]:
    """Get odometer readings for all devices in ONE API call."""
    cached = get_cached("maint:odometers", ttl=300)
    if cached is not None:
        return cached
    try:
        client = GeotabClient.get()
        data = client.get_status_data(
            diagnostic_id="DiagnosticOdometerId",
            from_date=datetime.now(timezone.utc) - timedelta(days=1),
        )
        result: dict[str, float] = {}
        for d in data:
            dev_id = d.get("device", {}).get("id", "")
            if dev_id:
                result[dev_id] = float(d.get("data", 0)) * 0.621371
        set_cached("maint:odometers", result)
        return result
    except (TimeoutError, Exception) as e:
        logger.warning(f"Failed to fetch odometers: {e}")
        return {}


def _get_fleet_engine_hours() -> dict[str, float]:
    cached = get_cached("maint:engine_hours", ttl=300)
    if cached is not None:
        return cached
    try:
        client = GeotabClient.get()
        data = client.get_status_data(
            diagnostic_id="DiagnosticEngineHoursId",
            from_date=datetime.now(timezone.utc) - timedelta(days=1),
        )
        result: dict[str, float] = {}
        for d in data:
            dev_id = d.get("device", {}).get("id", "")
            if dev_id:
                result[dev_id] = float(d.get("data", 0))
        set_cached("maint:engine_hours", result)
        return result
    except (TimeoutError, Exception) as e:
        logger.warning(f"Failed to fetch engine hours: {e}")
        return {}


def _get_fleet_faults(days: int | None = None) -> dict[str, list[dict]]:
    """Get fault data for ALL devices in ONE API call."""
    days = days or _fault_lookback_days()
    cached = get_cached(f"maint:faults:{days}", ttl=300)
    if cached is not None:
        return cached
    try:
        client = GeotabClient.get()
        fault_data = client._call(
            client.api.get, "FaultData",
            search={"fromDate": (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()},
        )
        result: dict[str, list[dict]] = {}
        for f in fault_data:
            dev_id = f.get("device", {}).get("id", "")
            if dev_id:
                result.setdefault(dev_id, []).append(f)
        set_cached(f"maint:faults:{days}", result)
        return result
    except (TimeoutError, Exception) as e:
        logger.warning(f"Failed to fetch faults: {e}")
        return {}


async def _fault_trends_from_data_connector(days: int) -> dict[str, Any]:
    try:
        from routers.data_connector import fault_trends

        return await fault_trends(days=days)
    except Exception as exc:
        logger.warning("Data Connector fault trend lookup failed: %s", exc)
        return {
            "faults": [],
            "period_days": days,
            "feed_status": "degraded",
            "message": str(exc),
        }


@router.get("/intelligence")
async def get_maintenance_intelligence(days: Annotated[int | None, Query(ge=1, le=90)] = None):
    days = days or _fault_lookback_days()
    cached = get_cached(f"maintenance_intelligence:{days}", ttl=300)
    if cached is not None:
        return cached

    devices = _get_devices_cached()
    fault_payload = await _fault_trends_from_data_connector(days)
    faults = fault_payload.get("faults") or []
    source_mode = "geotab_data_connector_fault_trends"

    if not faults:
        faults = _fallback_fault_rows_from_geotab(_get_fleet_faults(days), devices)
        source_mode = "geotab_fault_data_fallback"

    decisions = _build_maintenance_decisions(faults, days)
    summary = {
        "total_fault_rows": len(faults),
        "vehicles_with_faults": len({decision["vehicle_id"] for decision in decisions}),
        "critical": sum(1 for decision in decisions if decision["urgency"] == UrgencyLevel.CRITICAL),
        "high": sum(1 for decision in decisions if decision["urgency"] == UrgencyLevel.HIGH),
        "medium": sum(1 for decision in decisions if decision["urgency"] == UrgencyLevel.MEDIUM),
        "monitor": sum(1 for decision in decisions if decision["urgency"] == UrgencyLevel.LOW),
    }
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period_days": days,
        "source_authority": GEOTAB_MAINTENANCE_AUTHORITY,
        "projection_mode": "read_only_decision_support",
        "source_mode": source_mode,
        "feed_status": fault_payload.get("feed_status", "ok") if fault_payload else "ok",
        "automation_mode": "ai_recommends_human_executes",
        "learning_mode": {
            "enabled": True,
            "feedback_signal": "repair_outcome_and_code_clearance_evidence",
            "write_policy": "no_source_of_truth_overwrites",
        },
        "config": _maintenance_runtime_config(),
        "summary": summary,
        "decisions": decisions,
    }
    set_cached(f"maintenance_intelligence:{days}", result)
    return result


@router.get("/predictions", response_model=List[MaintenancePrediction])
async def get_maintenance_predictions():
    cached = get_cached("maintenance_predictions", ttl=300)
    if cached is not None:
        return cached
    try:
        devices = _get_devices_cached()
        odometers = _get_fleet_odometers()
        engine_hours_map = _get_fleet_engine_hours()
        lookback_days = _fault_lookback_days()
        faults_map = _get_fleet_faults(lookback_days)
        intelligence = await get_maintenance_intelligence(days=lookback_days)
        decision_by_vehicle = {
            decision["vehicle_id"]: decision
            for decision in intelligence.get("decisions", [])
        }

        predictions = []
        now = datetime.now(timezone.utc)
        intervals = _maintenance_intervals()
        costs = _maintenance_costs()

        for device in devices:
            device_id = device.get("id", "")
            device_name = device.get("name", "Unknown Vehicle")
            current_odometer = odometers.get(device_id, 0)
            engine_hours = engine_hours_map.get(device_id, 0)
            device_faults = faults_map.get(device_id, [])
            has_fault_codes = len(device_faults) > 0
            active_fault_count = len([f for f in device_faults if _fault_is_active(f)])
            ai_decision = decision_by_vehicle.get(device_id)

            base_date = now - timedelta(days=_service_baseline_days())
            base_odometer = max(0, current_odometer - _service_baseline_miles())

            upcoming_services = []
            for service_type in intervals:
                due_date, is_overdue = calculate_maintenance_due_date(
                    base_date, base_odometer, current_odometer, service_type
                )
                urgency = get_urgency_level(due_date, has_fault_codes)
                upcoming_services.append({
                    "service_type": service_type,
                    "due_date": due_date,
                    "is_overdue": is_overdue,
                    "urgency": urgency,
                    "estimated_cost": costs.get(service_type, 0),
                })

            predictions.append(MaintenancePrediction(
                vehicle_id=device_id, vehicle_name=device_name,
                current_odometer=current_odometer, engine_hours=engine_hours,
                upcoming_services=upcoming_services,
                has_active_fault_codes=has_fault_codes,
                active_fault_count=active_fault_count,
                ai_health_score=ai_decision.get("health_score", 100) if ai_decision else 100,
                ai_decision=ai_decision,
            ))

        set_cached("maintenance_predictions", predictions)
        return predictions

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get maintenance predictions: {str(e)}")


@router.get("/vehicle/{vehicle_id}", response_model=VehicleMaintenanceDetail)
async def get_vehicle_maintenance_detail(vehicle_id: str):
    cached = get_cached(f"maint:vehicle:{vehicle_id}", ttl=300)
    if cached is not None:
        return cached
    try:
        devices = _get_devices_cached()
        device = next((d for d in devices if d.get("id") == vehicle_id), None)
        if not device:
            raise HTTPException(status_code=404, detail="Vehicle not found")

        device_name = device.get("name", "Unknown Vehicle")
        odometers = _get_fleet_odometers()
        engine_hours_map = _get_fleet_engine_hours()
        lookback_days = _fault_lookback_days()
        faults_map = _get_fleet_faults(lookback_days)

        current_odometer = odometers.get(vehicle_id, 0)
        engine_hours = engine_hours_map.get(vehicle_id, 0)
        device_faults = faults_map.get(vehicle_id, [])
        intelligence = await get_maintenance_intelligence(days=lookback_days)
        ai_decision = next(
            (
                decision
                for decision in intelligence.get("decisions", [])
                if decision.get("vehicle_id") == vehicle_id
            ),
            None,
        )

        active_faults = []
        for fault in device_faults:
            if not fault.get("dismissDateTime"):
                active_faults.append({
                    "code": _fault_code_value(fault),
                    "description": _fault_description(fault),
                    "timestamp": _fault_seen_at(fault) or datetime.now(timezone.utc),
                    "severity": _fault_severity(fault),
                })

        now = datetime.now(timezone.utc)
        base_date = now - timedelta(days=_service_baseline_days())
        base_odometer = max(0, current_odometer - _service_baseline_miles())
        intervals = _maintenance_intervals()
        costs = _maintenance_costs()
        maintenance_history = []

        upcoming_services = []
        for service_type in intervals:
            due_date, is_overdue = calculate_maintenance_due_date(
                base_date, base_odometer, current_odometer, service_type
            )
            urgency = get_urgency_level(due_date, len(active_faults) > 0)
            upcoming_services.append({
                "service_type": service_type, "due_date": due_date,
                "is_overdue": is_overdue, "urgency": urgency,
                "estimated_cost": costs.get(service_type, 0),
            })

        result = VehicleMaintenanceDetail(
            vehicle_id=vehicle_id, vehicle_name=device_name,
            current_odometer=current_odometer, engine_hours=engine_hours,
            upcoming_services=upcoming_services,
            maintenance_history=maintenance_history,
            active_fault_codes=active_faults,
            last_service_date=None,
            ai_health_score=ai_decision.get("health_score", 100) if ai_decision else 100,
            ai_decision=ai_decision,
        )
        set_cached(f"maint:vehicle:{vehicle_id}", result)
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get vehicle maintenance detail: {str(e)}")


@router.get("/costs", response_model=MaintenanceCost)
async def get_maintenance_costs():
    cached = get_cached("maintenance_costs", ttl=300)
    if cached is not None:
        return cached
    try:
        devices = _get_devices_cached()
        odometers = _get_fleet_odometers()
        now = datetime.now(timezone.utc)
        primary_days = _forecast_primary_days()
        secondary_days = _forecast_secondary_days()
        next_primary = now + timedelta(days=primary_days)
        next_secondary = now + timedelta(days=secondary_days)
        intervals = _maintenance_intervals()
        costs = _maintenance_costs()

        total_cost_next_month = 0
        total_cost_next_3_months = 0
        cost_breakdown: dict[str, dict] = {}

        for device in devices:
            device_id = device.get("id", "")
            current_odometer = odometers.get(device_id, 0)
            base_date = now - timedelta(days=_service_baseline_days())
            base_odometer = max(0, current_odometer - _service_baseline_miles())

            for service_type in intervals:
                due_date, _ = calculate_maintenance_due_date(
                    base_date, base_odometer, current_odometer, service_type
                )
                cost = costs.get(service_type, 0)
                if due_date <= next_primary:
                    total_cost_next_month += cost
                    if service_type not in cost_breakdown:
                        cost_breakdown[service_type] = {"count": 0, "total_cost": 0}
                    cost_breakdown[service_type]["count"] += 1
                    cost_breakdown[service_type]["total_cost"] += cost
                if due_date <= next_secondary:
                    total_cost_next_3_months += cost

        average_monthly_cost = total_cost_next_3_months / max(secondary_days / _days_per_month(), 1)
        result = MaintenanceCost(
            total_cost_next_month=total_cost_next_month,
            total_cost_next_3_months=total_cost_next_3_months,
            cost_breakdown=cost_breakdown,
            average_monthly_cost=average_monthly_cost,
            forecast_primary_days=primary_days,
            forecast_secondary_days=secondary_days,
            cost_source="geotab_odometer_configured_service_intervals",
        )
        set_cached("maintenance_costs", result)
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get maintenance costs: {str(e)}")


@router.get("/urgent", response_model=List[UrgentMaintenanceAlert])
async def get_urgent_maintenance():
    cached = get_cached("maintenance_urgent", ttl=300)
    if cached is not None:
        return cached
    try:
        lookback_days = _fault_lookback_days()
        devices = _get_devices_cached()
        faults_map = _get_fleet_faults(lookback_days)
        odometers = _get_fleet_odometers()
        intervals = _maintenance_intervals()
        costs = _maintenance_costs()
        intelligence = get_cached(f"maintenance_intelligence:{lookback_days}", ttl=300) or {}
        decision_by_vehicle = {
            decision.get("vehicle_id"): decision
            for decision in intelligence.get("decisions", [])
            if decision.get("vehicle_id")
        }
        urgent_alerts = []
        now = datetime.now(timezone.utc)

        for device in devices:
            device_id = device.get("id", "")
            device_name = device.get("name", "Unknown Vehicle")
            active_faults = [f for f in faults_map.get(device_id, []) if _fault_is_active(f)]
            known_active_faults = [fault for fault in active_faults if not _fault_is_unknown(fault)]
            unknown_fault_count = len(active_faults) - len(known_active_faults)

            current_odometer = odometers.get(device_id, 0)
            base_date = now - timedelta(days=_service_baseline_days())
            base_odometer = max(0, current_odometer - _service_baseline_miles())

            overdue_services = []
            urgent_services = []

            for service_type in intervals:
                due_date, is_overdue = calculate_maintenance_due_date(
                    base_date, base_odometer, current_odometer, service_type
                )
                if is_overdue:
                    overdue_services.append({
                        "service_type": service_type, "due_date": due_date,
                        "days_overdue": (now - due_date).days,
                    })
                elif (due_date - now).days <= 7:
                    urgent_services.append({
                        "service_type": service_type, "due_date": due_date,
                        "days_until_due": (due_date - now).days,
                    })

            if active_faults or overdue_services or urgent_services:
                ai_urgency = _coerce_urgency((decision_by_vehicle.get(device_id) or {}).get("urgency"))
                fault_summary = _fault_code_summary(active_faults)
                suppressed_fault_count = max(0, len(_fault_insights(active_faults)) - len(fault_summary))
                if overdue_services:
                    urgency = UrgencyLevel.CRITICAL
                    triage_reason = "Scheduled service is overdue."
                elif known_active_faults and ai_urgency:
                    urgency = ai_urgency
                    triage_reason = "Geotab fault pattern has a maintenance decision."
                elif known_active_faults:
                    urgency = _fault_urgency_from_known_faults(known_active_faults) or UrgencyLevel.MEDIUM
                    triage_reason = "Known Geotab fault code needs maintenance review."
                elif active_faults:
                    urgency = (
                        UrgencyLevel.HIGH
                        if len(active_faults) >= _unknown_fault_high_count()
                        else UrgencyLevel.MEDIUM
                    )
                    triage_reason = "Unmapped Geotab diagnostic volume needs source mapping before repair dispatch."
                else:
                    urgency = UrgencyLevel.HIGH
                    triage_reason = "Scheduled service is due soon."

                alert = UrgentMaintenanceAlert(
                    vehicle_id=device_id, vehicle_name=device_name,
                    urgency=urgency,
                    active_fault_codes=fault_summary,
                    overdue_services=overdue_services,
                    urgent_services=urgent_services,
                    estimated_repair_cost=sum(
                        costs.get(s["service_type"], 0)
                        for s in overdue_services + urgent_services
                    ),
                    active_fault_count=len(active_faults),
                    known_fault_count=len(known_active_faults),
                    unknown_fault_count=unknown_fault_count,
                    suppressed_fault_count=suppressed_fault_count,
                    triage_reason=triage_reason,
                )
                urgent_alerts.append(alert)

        urgent_alerts.sort(key=lambda x: (_urgency_sort_value(x.urgency), -x.active_fault_count, x.vehicle_name))
        set_cached("maintenance_urgent", urgent_alerts)
        return urgent_alerts

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get urgent maintenance alerts: {str(e)}")
