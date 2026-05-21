"""Predictive maintenance endpoints – optimized with caching and timeouts."""

import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Query

from _cache import get_cached, set_cached
from geotab_client import GeotabClient
from models import (
    MaintenancePrediction,
    VehicleMaintenanceDetail,
    MaintenanceCost,
    UrgentMaintenanceAlert,
    MaintenanceType,
    UrgencyLevel,
)

logger = logging.getLogger(__name__)
router = APIRouter()

MAINTENANCE_INTERVALS = {
    "oil_change": {"miles": 5000, "months": 6},
    "brake_service": {"miles": 30000, "months": 24},
    "tire_rotation": {"miles": 7500, "months": 12},
    "transmission_service": {"miles": 60000, "months": 48},
}

MAINTENANCE_COSTS = {
    "oil_change": 75,
    "brake_service": 600,
    "tire_rotation": 25,
    "transmission_service": 300,
    "tires_replacement": 600,
}

FAULT_LOOKBACK_DAYS = 30
GEOTAB_MAINTENANCE_AUTHORITY = "K1 Logistics Inc / Geotab diagnostics"

CRITICAL_FAULT_TERMS = (
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

HIGH_FAULT_TERMS = (
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
    if any(term in text for term in CRITICAL_FAULT_TERMS):
        return "critical"
    if any(term in text for term in HIGH_FAULT_TERMS):
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
    if score >= 85:
        return (
            UrgencyLevel.CRITICAL,
            "hold_and_inspect_now",
            "Hold the asset for maintenance inspection before dispatch if operationally possible.",
        )
    if score >= 70:
        return (
            UrgencyLevel.HIGH,
            "schedule_repair_24h",
            "Schedule diagnosis or repair in the next 24 hours.",
        )
    if score >= 50:
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

        score = 25
        score += min(len(vehicle_faults) * 2, 20)
        score += min(active_count * 3, 18)
        score += min(len(recurring_codes) * 8, 16)
        score += min(persistent_count * 3, 12)
        if top["severity"] == "critical":
            score += 30
        elif top["severity"] == "high":
            score += 18
        elif top["severity"] == "medium":
            score += 10
        if latest_seen and (now - latest_seen) <= timedelta(days=3):
            score += 8
        risk_score = max(0, min(score, 100))
        urgency, decision, recommended_action = _decision_from_score(risk_score)
        confidence = min(
            0.96,
            0.42
            + min(len(vehicle_faults), 12) * 0.025
            + (0.14 if recurring_codes else 0)
            + (0.12 if active_count else 0)
            + (0.08 if latest_seen and (now - latest_seen) <= timedelta(days=7) else 0),
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


def _fault_code_summary(faults: list[dict], limit: int = 8) -> list[dict[str, str]]:
    summary = _fault_insights(faults)[:limit]
    return [
        {
            "code": item["code"],
            "description": (
                f"{item['description']} (x{item['count']})"
                if item["count"] > 1
                else item["description"]
            ),
        }
        for item in summary
    ]


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
    intervals = MAINTENANCE_INTERVALS[service_type]
    miles_since_service = current_odometer - odometer_at_service
    miles_remaining = intervals["miles"] - miles_since_service
    avg_miles_per_day = 50
    days_until_due = max(0, miles_remaining / avg_miles_per_day)
    due_date_by_miles = datetime.now(timezone.utc) + timedelta(days=days_until_due)
    due_date_by_time = last_service + timedelta(days=intervals["months"] * 30)
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


def _get_fleet_faults(days: int = FAULT_LOOKBACK_DAYS) -> dict[str, list[dict]]:
    """Get fault data for ALL devices in ONE API call."""
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
async def get_maintenance_intelligence(days: int = Query(30, ge=1, le=90)):
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
        faults_map = _get_fleet_faults()
        intelligence = await get_maintenance_intelligence(days=FAULT_LOOKBACK_DAYS)
        decision_by_vehicle = {
            decision["vehicle_id"]: decision
            for decision in intelligence.get("decisions", [])
        }

        predictions = []
        now = datetime.now(timezone.utc)

        for device in devices:
            device_id = device.get("id", "")
            device_name = device.get("name", "Unknown Vehicle")
            current_odometer = odometers.get(device_id, 0)
            engine_hours = engine_hours_map.get(device_id, 0)
            device_faults = faults_map.get(device_id, [])
            has_fault_codes = len(device_faults) > 0
            active_fault_count = len([f for f in device_faults if _fault_is_active(f)])
            ai_decision = decision_by_vehicle.get(device_id)

            base_date = now - timedelta(days=90)
            base_odometer = max(0, current_odometer - 3000)

            upcoming_services = []
            for service_type in MAINTENANCE_INTERVALS:
                due_date, is_overdue = calculate_maintenance_due_date(
                    base_date, base_odometer, current_odometer, service_type
                )
                urgency = get_urgency_level(due_date, has_fault_codes)
                upcoming_services.append({
                    "service_type": service_type,
                    "due_date": due_date,
                    "is_overdue": is_overdue,
                    "urgency": urgency,
                    "estimated_cost": MAINTENANCE_COSTS[service_type],
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
        faults_map = _get_fleet_faults()

        current_odometer = odometers.get(vehicle_id, 0)
        engine_hours = engine_hours_map.get(vehicle_id, 0)
        device_faults = faults_map.get(vehicle_id, [])
        intelligence = await get_maintenance_intelligence(days=FAULT_LOOKBACK_DAYS)
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
        base_date = now - timedelta(days=90)
        base_odometer = max(0, current_odometer - 3000)

        maintenance_history = []
        for i, service_type in enumerate(MAINTENANCE_INTERVALS):
            past_date = now - timedelta(days=90 + i * 30)
            maintenance_history.append({
                "service_type": service_type,
                "date": past_date,
                "odometer_at_service": max(0, current_odometer - (3000 - i * 500)),
                "cost": MAINTENANCE_COSTS[service_type],
                "notes": f"Completed {service_type.replace('_', ' ')} service",
            })

        upcoming_services = []
        for service_type in MAINTENANCE_INTERVALS:
            due_date, is_overdue = calculate_maintenance_due_date(
                base_date, base_odometer, current_odometer, service_type
            )
            urgency = get_urgency_level(due_date, len(active_faults) > 0)
            upcoming_services.append({
                "service_type": service_type, "due_date": due_date,
                "is_overdue": is_overdue, "urgency": urgency,
                "estimated_cost": MAINTENANCE_COSTS[service_type],
            })

        result = VehicleMaintenanceDetail(
            vehicle_id=vehicle_id, vehicle_name=device_name,
            current_odometer=current_odometer, engine_hours=engine_hours,
            upcoming_services=upcoming_services,
            maintenance_history=maintenance_history,
            active_fault_codes=active_faults,
            last_service_date=base_date,
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
        now = datetime.now(timezone.utc)
        next_month = now + timedelta(days=30)
        next_3_months = now + timedelta(days=90)

        total_cost_next_month = 0
        total_cost_next_3_months = 0
        cost_breakdown: dict[str, dict] = {}

        for device in devices:
            current_odometer = 15000
            base_date = now - timedelta(days=90)
            base_odometer = current_odometer - 3000

            for service_type in MAINTENANCE_INTERVALS:
                due_date, _ = calculate_maintenance_due_date(
                    base_date, base_odometer, current_odometer, service_type
                )
                cost = MAINTENANCE_COSTS[service_type]
                if due_date <= next_month:
                    total_cost_next_month += cost
                    if service_type not in cost_breakdown:
                        cost_breakdown[service_type] = {"count": 0, "total_cost": 0}
                    cost_breakdown[service_type]["count"] += 1
                    cost_breakdown[service_type]["total_cost"] += cost
                if due_date <= next_3_months:
                    total_cost_next_3_months += cost

        result = MaintenanceCost(
            total_cost_next_month=total_cost_next_month,
            total_cost_next_3_months=total_cost_next_3_months,
            cost_breakdown=cost_breakdown,
            average_monthly_cost=total_cost_next_3_months / 3,
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
        devices = _get_devices_cached()
        faults_map = _get_fleet_faults()
        urgent_alerts = []
        now = datetime.now(timezone.utc)

        for device in devices:
            device_id = device.get("id", "")
            device_name = device.get("name", "Unknown Vehicle")
            active_faults = [f for f in faults_map.get(device_id, []) if _fault_is_active(f)]

            current_odometer = 15000
            base_date = now - timedelta(days=90)
            base_odometer = current_odometer - 3000

            overdue_services = []
            urgent_services = []

            for service_type in MAINTENANCE_INTERVALS:
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
                urgency = UrgencyLevel.CRITICAL if (active_faults or overdue_services) else UrgencyLevel.HIGH
                alert = UrgentMaintenanceAlert(
                    vehicle_id=device_id, vehicle_name=device_name,
                    urgency=urgency,
                    active_fault_codes=_fault_code_summary(active_faults),
                    overdue_services=overdue_services,
                    urgent_services=urgent_services,
                    estimated_repair_cost=sum(
                        MAINTENANCE_COSTS.get(s["service_type"], 0)
                        for s in overdue_services + urgent_services
                    ),
                )
                urgent_alerts.append(alert)

        urgent_alerts.sort(key=lambda x: (x.urgency.value, x.vehicle_name))
        set_cached("maintenance_urgent", urgent_alerts)
        return urgent_alerts

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get urgent maintenance alerts: {str(e)}")
