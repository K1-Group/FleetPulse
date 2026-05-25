"""Compliance & ELD (Electronic Logging Device) read-only endpoints."""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter
from typing import Any

from geotab_client import GeotabClient
from _cache import get_cached, set_cached

router = APIRouter()

SOURCE_AUTHORITY = "K1 Logistics Inc / Geotab trip and device telemetry"
HOS_EVIDENCE_MODE = "geotab_trip_activity_proxy"
DVIR_SOURCE_AUTHORITY = "K1 Logistics Inc / Geotab device telemetry + configured DVIR evidence feeds"

# FMCSA HOS limits
HOS_LIMITS = {
    "daily_driving": 11,      # hours
    "daily_on_duty": 14,      # hours
    "weekly_on_duty": 60,     # hours (7-day)
    "rest_break": 0.5,        # 30 min break required after 8h driving
}


@router.get("/hos-summary")
async def hos_summary():
    """Get a Geotab trip-activity HOS risk proxy for the fleet.

    This endpoint deliberately does not claim certified ELD driver-log compliance.
    If the Geotab read path is unavailable, it returns an explicit unavailable
    state instead of demo driver counts or fabricated violations.
    """
    cache_key = "compliance:hos"
    cached = get_cached(cache_key)
    if cached:
        return cached

    try:
        client = GeotabClient.get()
        now = datetime.now(timezone.utc)
        
        devices = client.get_devices()
        trips_7d = client.get_trips(from_date=now - timedelta(days=7), to_date=now)
        trips_today = [t for t in trips_7d if _parse_date(t.get("start", "")) > now - timedelta(days=1)]
        
        # Calculate per-device driving hours
        device_names = {d.get("id", ""): d.get("name", "Unknown") for d in devices}
        device_hours_today: dict[str, float] = {}
        device_hours_week: dict[str, float] = {}
        
        for t in trips_7d:
            dev = t.get("device", {})
            dev_id = dev.get("id", "") if isinstance(dev, dict) else ""
            
            # Calculate trip duration in hours
            start = _parse_date(t.get("start", ""))
            stop = _parse_date(t.get("stop", ""))
            duration_h = (stop - start).total_seconds() / 3600
            duration_h = max(0, min(duration_h, 24))  # sanity clamp
            
            device_hours_week[dev_id] = device_hours_week.get(dev_id, 0) + duration_h
            
            if start > now - timedelta(days=1):
                device_hours_today[dev_id] = device_hours_today.get(dev_id, 0) + duration_h
        
        # Check violations
        violations = []
        compliant_count = 0
        warning_count = 0
        violation_count = 0
        
        driver_statuses = []
        
        for dev_id in set(list(device_hours_today.keys()) + list(device_hours_week.keys())):
            today_h = device_hours_today.get(dev_id, 0)
            week_h = device_hours_week.get(dev_id, 0)
            name = device_names.get(dev_id, dev_id)
            
            daily_pct = (today_h / HOS_LIMITS["daily_driving"]) * 100
            weekly_pct = (week_h / HOS_LIMITS["weekly_on_duty"]) * 100
            
            status = "compliant"
            
            if today_h > HOS_LIMITS["daily_driving"]:
                status = "violation"
                violation_count += 1
                violations.append({
                    "vehicle": name,
                    "type": "daily_driving_exceeded",
                    "hours": round(today_h, 1),
                    "limit": HOS_LIMITS["daily_driving"],
                    "severity": "high",
                })
            elif week_h > HOS_LIMITS["weekly_on_duty"]:
                status = "violation"
                violation_count += 1
                violations.append({
                    "vehicle": name,
                    "type": "weekly_on_duty_exceeded",
                    "hours": round(week_h, 1),
                    "limit": HOS_LIMITS["weekly_on_duty"],
                    "severity": "critical",
                })
            elif today_h > HOS_LIMITS["daily_driving"] * 0.8 or week_h > HOS_LIMITS["weekly_on_duty"] * 0.8:
                status = "warning"
                warning_count += 1
            else:
                compliant_count += 1
            
            driver_statuses.append({
                "vehicle_id": dev_id,
                "vehicle_name": name,
                "status": status,
                "today_hours": round(today_h, 1),
                "today_remaining": round(max(0, HOS_LIMITS["daily_driving"] - today_h), 1),
                "today_pct": min(round(daily_pct, 0), 100),
                "week_hours": round(week_h, 1),
                "week_remaining": round(max(0, HOS_LIMITS["weekly_on_duty"] - week_h), 1),
                "week_pct": min(round(weekly_pct, 0), 100),
            })
        
        driver_statuses.sort(key=lambda x: x["today_hours"], reverse=True)
        
        result = {
            "summary": {
                "total_drivers": len(driver_statuses),
                "compliant": compliant_count,
                "warnings": warning_count,
                "violations": violation_count,
                "compliance_rate": round(compliant_count / max(len(driver_statuses), 1) * 100, 1),
            },
            "limits": HOS_LIMITS,
            "violations": violations[:10],
            "drivers": driver_statuses[:30],
            "last_updated": now.isoformat(),
            "source_authority": SOURCE_AUTHORITY,
            "projection_mode": "read_only",
            "evidence_mode": HOS_EVIDENCE_MODE,
            "source_status": {
                "status": "healthy",
                "message": "Uses Geotab trip durations as a HOS risk proxy; certified ELD driver-log feed is not configured.",
                "device_count": len(devices),
                "trip_count_7d": len(trips_7d),
                "trip_count_today": len(trips_today),
            },
        }
        
        set_cached(cache_key, result, ttl=120)
        return result
        
    except Exception as e:
        return _hos_unavailable(e)


@router.get("/inspection-readiness")
async def inspection_readiness():
    """Get source-backed inspection readiness coverage.

    Items without a configured source feed are returned as awaiting_feed instead
    of being counted as passed.
    """
    cache_key = "compliance:dvir"
    cached = get_cached(cache_key)
    if cached:
        return cached

    try:
        client = GeotabClient.get()
        devices = client.get_devices()
        now = datetime.now(timezone.utc)
        device_status_error = None
        trip_error = None

        try:
            device_status = client.get_device_status_info()
        except Exception as exc:  # pragma: no cover - depends on live Geotab permissions
            device_status = []
            device_status_error = str(exc)

        try:
            trips_7d = client.get_trips(from_date=now - timedelta(days=7), to_date=now)
        except Exception as exc:  # pragma: no cover - depends on live Geotab permissions
            trips_7d = []
            trip_error = str(exc)

        device_count = len(devices)
        status_device_ids = {
            _device_id(item.get("device"))
            for item in device_status
            if _device_id(item.get("device"))
        }
        trip_device_ids = {
            _device_id(item.get("device"))
            for item in trips_7d
            if _device_id(item.get("device"))
        }

        checklist_items = [
            _checklist_item(
                "ELD Device Connected",
                "pass" if device_count else "warning",
                "Geotab Device inventory",
                f"{device_count} Geotab device(s) returned.",
                "📡",
            ),
            _checklist_item(
                "GPS Signal Active",
                "pass" if status_device_ids else "warning",
                "Geotab DeviceStatusInfo",
                (
                    f"{len(status_device_ids)} device(s) returned live status."
                    if not device_status_error
                    else f"DeviceStatusInfo unavailable: {device_status_error}"
                ),
                "📍",
            ),
            _checklist_item(
                "HOS Records (7-day)",
                "pass" if trip_device_ids else "warning",
                "Geotab Trip activity proxy",
                (
                    f"{len(trips_7d)} trip row(s) across {len(trip_device_ids)} device(s)."
                    if not trip_error
                    else f"Trip activity unavailable: {trip_error}"
                ),
                "📋",
            ),
            _checklist_item(
                "Driver Identification",
                "awaiting_feed",
                "Xcelerator driver assignment or certified ELD driver-log feed",
                "No configured source-backed driver identification feed is connected to this readiness endpoint.",
                "🪪",
            ),
            _checklist_item(
                "Vehicle Registration",
                "awaiting_feed",
                "SharePoint document register",
                "No configured registration document feed is connected to this readiness endpoint.",
                "📄",
            ),
            _checklist_item(
                "Insurance Documentation",
                "awaiting_feed",
                "SharePoint or insurance document register",
                "No configured insurance document feed is connected to this readiness endpoint.",
                "🛡️",
            ),
            _checklist_item(
                "Pre-trip Inspection Log",
                "awaiting_feed",
                "DVIR inspection feed",
                "No configured pre-trip DVIR completion feed is connected.",
                "🔍",
            ),
            _checklist_item(
                "Post-trip Inspection Log",
                "awaiting_feed",
                "DVIR inspection feed",
                "No configured post-trip DVIR completion feed is connected.",
                "✅",
            ),
        ]

        scored_items = [c for c in checklist_items if c["status"] in {"pass", "warning", "fail", "unavailable"}]
        pass_count = len([c for c in scored_items if c["status"] == "pass"])
        awaiting_count = len([c for c in checklist_items if c["status"] == "awaiting_feed"])
        
        result = {
            "overall_score": round(pass_count / max(len(scored_items), 1) * 100, 0),
            "status": "ready" if pass_count == len(scored_items) and awaiting_count == 0 else "needs_review",
            "checklist": checklist_items,
            "total_vehicles": device_count,
            "vehicles_inspected_today": None,
            "last_audit_date": None,
            "next_audit_date": None,
            "source_authority": DVIR_SOURCE_AUTHORITY,
            "projection_mode": "read_only",
            "source_status": {
                "status": "partial" if awaiting_count else "healthy",
                "message": "Geotab device telemetry is connected; DVIR/document feeds are awaiting source-backed integration.",
                "device_count": device_count,
                "device_status_count": len(status_device_ids),
                "trip_count_7d": len(trips_7d),
                "awaiting_feed_count": awaiting_count,
            },
        }
        
        set_cached(cache_key, result, ttl=300)
        return result
        
    except Exception as e:
        return _inspection_unavailable(e)


def _parse_date(date_str) -> datetime:
    try:
        if isinstance(date_str, datetime):
            return date_str
        return datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
    except:
        return datetime.now(timezone.utc) - timedelta(days=999)


def _device_id(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("id") or "")
    return ""


def _checklist_item(
    item: str,
    status: str,
    source: str,
    detail: str,
    icon: str,
) -> dict[str, str]:
    return {
        "item": item,
        "status": status,
        "source": source,
        "detail": detail,
        "icon": icon,
    }


def _hos_unavailable(exc: Exception) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "summary": {
            "total_drivers": 0,
            "compliant": 0,
            "warnings": 0,
            "violations": 0,
            "compliance_rate": 0.0,
        },
        "limits": HOS_LIMITS,
        "violations": [],
        "drivers": [],
        "last_updated": now.isoformat(),
        "source_authority": SOURCE_AUTHORITY,
        "projection_mode": "read_only",
        "evidence_mode": HOS_EVIDENCE_MODE,
        "source_status": {
            "status": "unavailable",
            "message": f"Geotab trip activity is unavailable: {type(exc).__name__}: {exc}",
            "device_count": 0,
            "trip_count_7d": 0,
            "trip_count_today": 0,
        },
    }


def _inspection_unavailable(exc: Exception) -> dict[str, Any]:
    return {
        "overall_score": 0,
        "status": "unavailable",
        "checklist": [
            _checklist_item(
                "ELD Device Connected",
                "unavailable",
                "Geotab Device inventory",
                f"Geotab device inventory is unavailable: {type(exc).__name__}: {exc}",
                "📡",
            ),
            _checklist_item(
                "GPS Signal Active",
                "unavailable",
                "Geotab DeviceStatusInfo",
                "Device status cannot be validated until Geotab is reachable.",
                "📍",
            ),
            _checklist_item(
                "HOS Records (7-day)",
                "unavailable",
                "Geotab Trip activity proxy",
                "Trip activity cannot be validated until Geotab is reachable.",
                "📋",
            ),
            _checklist_item(
                "Driver Identification",
                "awaiting_feed",
                "Xcelerator driver assignment or certified ELD driver-log feed",
                "No configured source-backed driver identification feed is connected to this readiness endpoint.",
                "🪪",
            ),
        ],
        "total_vehicles": 0,
        "vehicles_inspected_today": None,
        "last_audit_date": None,
        "next_audit_date": None,
        "source_authority": DVIR_SOURCE_AUTHORITY,
        "projection_mode": "read_only",
        "source_status": {
            "status": "unavailable",
            "message": f"Inspection readiness source unavailable: {type(exc).__name__}: {exc}",
            "device_count": 0,
            "device_status_count": 0,
            "trip_count_7d": 0,
            "awaiting_feed_count": 1,
        },
    }
