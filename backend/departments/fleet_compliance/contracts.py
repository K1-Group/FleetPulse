"""Fleet & Compliance department contracts."""

from typing import Any

DEPARTMENT_ID = "fleet_compliance"
SEAT_ID = "fleet_compliance_manager"

DASHBOARD_TABS: list[str] = [
    "dashboard",
    "control-tower",
    "maintenance",
    "coaching",
    "replay",
    "geofences",
    "fuel",
    "compliance",
    "data-connector",
]

ComplianceSnapshot = dict[str, Any]
