"""Alert service — anomaly detection, configurable rules, alert history."""

from __future__ import annotations

import hashlib
import os
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from geotab_client import GeotabClient
from models import Alert, AlertRule, AlertSeverity

# ── Default alert rules ────────────────────────────────────────
DEFAULT_RULES: list[AlertRule] = [
    AlertRule(id="speed_high", name="High Speed", description="Vehicle exceeds 120 km/h", enabled=True, threshold=120, alert_type="speeding", severity=AlertSeverity.HIGH),
    AlertRule(id="speed_extreme", name="Extreme Speed", description="Vehicle exceeds 150 km/h", enabled=True, threshold=150, alert_type="speeding", severity=AlertSeverity.CRITICAL),
    AlertRule(id="idle_long", name="Extended Idle", description="Vehicle idle >30 min", enabled=True, threshold=30, alert_type="idle", severity=AlertSeverity.MEDIUM),
    AlertRule(id="geofence_exit", name="Geofence Breach", description="Vehicle left assigned zone", enabled=True, threshold=None, alert_type="geofence", severity=AlertSeverity.HIGH),
    AlertRule(id="after_hours", name="After Hours Usage", description="Vehicle moving between 11PM-5AM", enabled=True, threshold=None, alert_type="after_hours", severity=AlertSeverity.MEDIUM),
]

_alert_rules = list(DEFAULT_RULES)
_ALERT_CACHE: dict[str, tuple[float, list[Alert]]] = {}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _cache_ttl_seconds() -> int:
    return max(0, _int_env("FLEETPULSE_CACHE_TTL_SECONDS", 30))


def _cache_fallback_seconds() -> int:
    return max(_cache_ttl_seconds(), _int_env("FLEETPULSE_CACHE_FALLBACK_SECONDS", 300))


def _cache_get(key: str, max_age_seconds: int) -> list[Alert] | None:
    if max_age_seconds <= 0:
        return None
    entry = _ALERT_CACHE.get(key)
    if not entry:
        return None
    created_at, alerts = entry
    if time.time() - created_at > max_age_seconds:
        return None
    return deepcopy(alerts)


def _cache_set(key: str, alerts: list[Alert]) -> None:
    _ALERT_CACHE[key] = (time.time(), deepcopy(alerts))


def _event_to_alert(event: dict[str, Any], devices: dict[str, str]) -> Alert | None:
    """Convert a Geotab ExceptionEvent into an Alert."""
    dev_id = event.get("device", {}).get("id", "")
    rule_name = event.get("rule", {}).get("name", "")
    ts = event.get("activeFrom") or event.get("dateTime") or datetime.now(timezone.utc)

    # Determine severity from rule name
    lower = rule_name.lower()
    if any(w in lower for w in ["extreme", "critical"]):
        severity = AlertSeverity.CRITICAL
    elif any(w in lower for w in ["speed", "geofence", "zone"]):
        severity = AlertSeverity.HIGH
    elif any(w in lower for w in ["harsh", "hard", "idle"]):
        severity = AlertSeverity.MEDIUM
    else:
        severity = AlertSeverity.LOW

    uid = hashlib.sha256(f"{dev_id}{rule_name}{ts}".encode()).hexdigest()[:12]

    return Alert(
        id=uid,
        vehicle_id=dev_id,
        vehicle_name=devices.get(dev_id, "Unknown"),
        alert_type=rule_name,
        severity=severity,
        message=f"{rule_name} detected on {devices.get(dev_id, dev_id)}",
        timestamp=ts if isinstance(ts, datetime) else datetime.now(timezone.utc),
    )


def get_recent_alerts(hours: int = 24) -> list[Alert]:
    cache_key = f"recent:{hours}"
    cached = _cache_get(cache_key, _cache_ttl_seconds())
    if cached is not None:
        return cached

    client = GeotabClient.get()
    try:
        devices = {d["id"]: d.get("name", "Unknown") for d in client.get_devices()}
        now = datetime.now(timezone.utc)
        events = client.get_exception_events(now - timedelta(hours=hours), now)
    except TimeoutError:
        fallback = _cache_get(cache_key, _cache_fallback_seconds())
        return fallback if fallback is not None else []

    alerts: list[Alert] = []
    for e in events:
        a = _event_to_alert(e, devices)
        if a:
            alerts.append(a)

    alerts.sort(key=lambda a: a.timestamp, reverse=True)
    result = alerts[:100]  # cap at 100
    _cache_set(cache_key, result)
    return result


def get_alert_rules() -> list[AlertRule]:
    return _alert_rules


def update_alert_rule(rule_id: str, enabled: bool | None = None, threshold: float | None = None) -> AlertRule | None:
    for r in _alert_rules:
        if r.id == rule_id:
            if enabled is not None:
                r.enabled = enabled
            if threshold is not None:
                r.threshold = threshold
            return r
    return None
