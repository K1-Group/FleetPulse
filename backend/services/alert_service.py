"""Alert service — anomaly detection, configurable rules, alert history."""

from __future__ import annotations

import hashlib
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
    client = GeotabClient.get()
    devices = {d["id"]: d.get("name", "Unknown") for d in client.get_devices()}
    now = datetime.now(timezone.utc)
    events = client.get_exception_events(now - timedelta(hours=hours), now)

    alerts: list[Alert] = []
    for e in events:
        a = _event_to_alert(e, devices)
        if a:
            alerts.append(a)

    alerts.sort(key=lambda a: a.timestamp, reverse=True)
    return alerts[:100]  # cap at 100


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
