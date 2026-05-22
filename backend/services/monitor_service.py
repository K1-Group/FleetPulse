"""Agentic Monitor — intelligent anomaly detection and proactive alerting.

This is FleetPulse's key differentiator: an autonomous monitoring agent that
continuously analyzes fleet telemetry, detects anomalies, identifies patterns,
and generates proactive alerts with severity levels and recommendations.

The monitor runs periodic checks and maintains an in-memory alert history
with pattern tracking across the configured K1 Logistics operating hubs.
"""

from __future__ import annotations

import hashlib
import statistics
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from geotab_client import GeotabClient
from models import Alert, AlertSeverity
from services.fleet_service import LOCATIONS

# ── In-memory state ────────────────────────────────────────────
_alert_history: list[Alert] = []
_alert_lock = threading.Lock()
_pattern_data: dict[str, Any] = {}
_monitor_running = False
_monitor_thread: threading.Thread | None = None

# K1 Logistics location centers for geofence checks.
LOCATION_CENTERS = {location["name"]: (location["lat"], location["lon"]) for location in LOCATIONS}

# K1 operations bounding box around configured operating hubs.
OPS_BOUNDS = {
    "lat_min": min(lat for lat, _lon in LOCATION_CENTERS.values()) - 0.5,
    "lat_max": max(lat for lat, _lon in LOCATION_CENTERS.values()) + 0.5,
    "lon_min": min(lon for _lat, lon in LOCATION_CENTERS.values()) - 0.5,
    "lon_max": max(lon for _lat, lon in LOCATION_CENTERS.values()) + 0.5,
}

# K1 speeding threshold: 6 mph (~10 km/h) over posted speed limit
SPEEDING_THRESHOLD_MPH = 6
SPEEDING_THRESHOLD_KMH = 10  # approximate conversion
KMH_TO_MPH = 0.621371


def _format_mph(speed_kmh: float) -> str:
    return f"{speed_kmh * KMH_TO_MPH:.0f} mph"


def _uid(parts: str) -> str:
    return hashlib.md5(parts.encode()).hexdigest()[:12]


def _add_alert(alert: Alert) -> None:
    with _alert_lock:
        # Deduplicate by id
        existing_ids = {a.id for a in _alert_history[-500:]}
        if alert.id not in existing_ids:
            _alert_history.append(alert)
            # Keep last 1000
            if len(_alert_history) > 1000:
                _alert_history[:] = _alert_history[-1000:]


def _make_alert(
    vehicle_id: str,
    vehicle_name: str,
    alert_type: str,
    severity: AlertSeverity,
    message: str,
    recommendation: str = "",
) -> Alert:
    now = datetime.now(timezone.utc)
    uid = _uid(f"{vehicle_id}{alert_type}{now.strftime('%Y%m%d%H')}")
    full_msg = f"{message}"
    if recommendation:
        full_msg += f" 💡 {recommendation}"
    return Alert(
        id=uid,
        vehicle_id=vehicle_id,
        vehicle_name=vehicle_name,
        alert_type=alert_type,
        severity=severity,
        message=full_msg,
        timestamp=now,
    )


# ── Anomaly Detection Checks ──────────────────────────────────

def check_speed_anomalies(statuses: list[dict], device_map: dict[str, str]) -> list[Alert]:
    """Detect vehicles exceeding speed threshold (6 mph / 10 km/h over limit)."""
    alerts = []
    for s in statuses:
        speed = s.get("speed", 0) or 0
        dev_id = s.get("device", {}).get("id", "")
        name = device_map.get(dev_id, "Unknown")

        if speed > 140:
            alerts.append(_make_alert(
                dev_id, name, "extreme_speed", AlertSeverity.CRITICAL,
                f"⚠️ {name} traveling at {_format_mph(speed)} — dangerously above limit",
                "Immediate intervention recommended. Contact driver."
            ))
        elif speed > 120:
            alerts.append(_make_alert(
                dev_id, name, "high_speed", AlertSeverity.HIGH,
                f"🚨 {name} at {_format_mph(speed)} — significantly above speed limit",
                "Review driver behavior pattern."
            ))
    return alerts


def check_excessive_idling(statuses: list[dict], device_map: dict[str, str]) -> list[Alert]:
    """Detect vehicles that have been idling excessively."""
    alerts = []
    for s in statuses:
        speed = s.get("speed", 0) or 0
        is_driving = s.get("isDriving", False)
        duration = s.get("currentStateDuration")
        dev_id = s.get("device", {}).get("id", "")
        name = device_map.get(dev_id, "Unknown")

        # If not driving and has been in current state for a while
        if not is_driving and speed == 0 and duration:
            # currentStateDuration is a time object
            try:
                if hasattr(duration, 'hour'):
                    minutes = duration.hour * 60 + duration.minute
                else:
                    minutes = 0
            except Exception:
                minutes = 0

            if minutes > 120:
                alerts.append(_make_alert(
                    dev_id, name, "excessive_idle", AlertSeverity.MEDIUM,
                    f"🟡 {name} idle for {minutes} min — extended idle detected",
                    "Check if vehicle is abandoned or unauthorized stop."
                ))
            elif minutes > 60:
                alerts.append(_make_alert(
                    dev_id, name, "long_idle", AlertSeverity.LOW,
                    f"💤 {name} idle for {minutes} min at current location",
                    "Monitor for extended pattern."
                ))
    return alerts


def check_off_route_vehicles(statuses: list[dict], device_map: dict[str, str]) -> list[Alert]:
    """Detect vehicles that are outside the K1 operations area."""
    alerts = []
    for s in statuses:
        lat = s.get("latitude", 0) or 0
        lon = s.get("longitude", 0) or 0
        dev_id = s.get("device", {}).get("id", "")
        name = device_map.get(dev_id, "Unknown")

        if lat == 0 and lon == 0:
            continue

        if (lat < OPS_BOUNDS["lat_min"] or lat > OPS_BOUNDS["lat_max"] or
            lon < OPS_BOUNDS["lon_min"] or lon > OPS_BOUNDS["lon_max"]):
            alerts.append(_make_alert(
                dev_id, name, "off_route", AlertSeverity.HIGH,
                f"🗺️ {name} detected outside K1 operations area ({lat:.4f}, {lon:.4f})",
                "Verify if authorized trip. May indicate unauthorized use."
            ))
    return alerts


def check_after_hours(statuses: list[dict], device_map: dict[str, str]) -> list[Alert]:
    """Detect vehicles driving during off-hours (11 PM - 5 AM local)."""
    # Central Time is UTC-6 (CDT) / UTC-5 (CST)
    now_utc = datetime.now(timezone.utc)
    local_hour = (now_utc.hour - 6) % 24

    if not (local_hour >= 23 or local_hour < 5):
        return []

    alerts = []
    for s in statuses:
        is_driving = s.get("isDriving", False)
        speed = s.get("speed", 0) or 0
        dev_id = s.get("device", {}).get("id", "")
        name = device_map.get(dev_id, "Unknown")

        if is_driving or speed > 5:
            alerts.append(_make_alert(
                dev_id, name, "after_hours", AlertSeverity.MEDIUM,
                f"🌙 {name} active during off-hours (local {local_hour}:00)",
                "After-hours usage flagged for review."
            ))
    return alerts


def check_fleet_patterns(statuses: list[dict], device_map: dict[str, str]) -> list[Alert]:
    """Analyze fleet-wide patterns for anomalies."""
    alerts = []
    speeds = [s.get("speed", 0) or 0 for s in statuses if s.get("isDriving")]
    active_count = sum(1 for s in statuses if s.get("isDriving"))
    total = len(statuses)

    if total > 0:
        active_pct = active_count / total * 100

        # Unusual fleet activity level
        now_utc = datetime.now(timezone.utc)
        local_hour = (now_utc.hour - 6) % 24

        # Late night with high activity is suspicious
        if (local_hour >= 23 or local_hour < 5) and active_pct > 40:
            alerts.append(_make_alert(
                "fleet", "Fleet-wide", "unusual_activity", AlertSeverity.HIGH,
                f"📊 {active_pct:.0f}% of fleet active during off-hours ({active_count}/{total})",
                "Unusual fleet-wide activity pattern detected."
            ))

        # Check speed distribution
        if speeds and len(speeds) > 3:
            avg_speed = statistics.mean(speeds)
            if avg_speed > 80:
                alerts.append(_make_alert(
                    "fleet", "Fleet-wide", "high_avg_speed", AlertSeverity.MEDIUM,
                    f"📈 Fleet average speed unusually high: {_format_mph(avg_speed)} across {len(speeds)} active vehicles",
                    "Review driver training compliance."
                ))

    return alerts


def check_location_imbalances(statuses: list[dict], device_map: dict[str, str]) -> list[Alert]:
    """Detect location inventory imbalances."""
    # Count vehicles near each location
    loc_counts: dict[str, int] = {name: 0 for name in LOCATION_CENTERS}
    for s in statuses:
        lat = s.get("latitude", 0) or 0
        lon = s.get("longitude", 0) or 0
        for name, (clat, clon) in LOCATION_CENTERS.items():
            dist = ((lat - clat) ** 2 + (lon - clon) ** 2) ** 0.5
            if dist < 0.005:
                loc_counts[name] += 1
                break

    # Alert if any location is severely imbalanced
    counts = [c for c in loc_counts.values() if c > 0]
    alerts = []
    if counts:
        avg = statistics.mean(counts)
        for name, count in loc_counts.items():
            if count == 0:
                alerts.append(_make_alert(
                    "loc_" + name.replace(" ", "_"), name,
                    "empty_location", AlertSeverity.HIGH,
                    f"📍 {name} has 0 vehicles — location may need inventory rebalance",
                    "Consider dispatching vehicles from nearby locations."
                ))
            elif avg > 0 and count > avg * 2.5:
                alerts.append(_make_alert(
                    "loc_" + name.replace(" ", "_"), name,
                    "location_overstock", AlertSeverity.LOW,
                    f"📍 {name} has {count} vehicles (fleet avg: {avg:.0f}) — possible overstock",
                    "Consider redistributing to lower-inventory locations."
                ))
    return alerts


# ── Main Monitor Loop ──────────────────────────────────────────

def _run_all_checks() -> list[Alert]:
    """Execute all anomaly detection checks and return generated alerts."""
    try:
        client = GeotabClient.get()
        statuses = client.get_device_status_info()
        devices = client.get_devices()
        device_map = {d["id"]: d.get("name", "Unknown") for d in devices}

        all_alerts: list[Alert] = []
        all_alerts.extend(check_speed_anomalies(statuses, device_map))
        all_alerts.extend(check_excessive_idling(statuses, device_map))
        all_alerts.extend(check_off_route_vehicles(statuses, device_map))
        all_alerts.extend(check_after_hours(statuses, device_map))
        all_alerts.extend(check_fleet_patterns(statuses, device_map))
        all_alerts.extend(check_location_imbalances(statuses, device_map))

        for alert in all_alerts:
            _add_alert(alert)

        # Update pattern data
        global _pattern_data
        _pattern_data = {
            "last_check": datetime.now(timezone.utc).isoformat(),
            "total_vehicles": len(devices),
            "active_vehicles": sum(1 for s in statuses if s.get("isDriving")),
            "alerts_generated": len(all_alerts),
            "checks_run": 6,
            "location_vehicle_counts": {
                name: sum(1 for s in statuses
                    if ((s.get("latitude", 0) or 0) - center[0]) ** 2 +
                       ((s.get("longitude", 0) or 0) - center[1]) ** 2 < 0.005 ** 2)
                for name, center in LOCATION_CENTERS.items()
            },
        }

        return all_alerts
    except Exception as e:
        print(f"[Monitor] Check failed: {e}")
        return []


def _monitor_loop():
    """Background loop that runs checks every 60 seconds."""
    global _monitor_running
    while _monitor_running:
        _run_all_checks()
        # Sleep 60s in 1s increments so we can stop quickly
        for _ in range(60):
            if not _monitor_running:
                break
            time.sleep(1)


def start_monitor():
    """Start the background agentic monitor."""
    global _monitor_running, _monitor_thread
    if _monitor_running:
        return
    _monitor_running = True
    _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
    _monitor_thread.start()
    # Run initial check immediately
    _run_all_checks()
    print("[Monitor] Agentic monitor started — checking every 60s")


def stop_monitor():
    """Stop the background monitor."""
    global _monitor_running
    _monitor_running = False


# ── Public API ─────────────────────────────────────────────────

def get_monitor_alerts(limit: int = 50) -> list[Alert]:
    """Get recent agentic monitor alerts."""
    with _alert_lock:
        return sorted(_alert_history[-limit:], key=lambda a: a.timestamp, reverse=True)


def get_monitor_status() -> dict[str, Any]:
    """Get current monitor status and pattern data."""
    return {
        "running": _monitor_running,
        "total_alerts": len(_alert_history),
        "patterns": _pattern_data,
    }


def run_check_now() -> list[Alert]:
    """Manually trigger a check cycle."""
    return _run_all_checks()
