"""Executive department contracts.

Lightweight typed surface describing what the executive dashboard expects from
its services. These mirror current API shapes rather than introducing new
fields, so they can be tightened over time without changing behavior today.
"""

from typing import Any

DEPARTMENT_ID = "executive"
SEAT_ID = "executive_command"

DASHBOARD_TABS: list[str] = [
    "dashboard",
    "control-tower",
    "finance",
    "operating-system",
    "hr-recruiting",
    "maintenance",
    "coaching",
    "replay",
    "stability",
    "reports",
    "geofences",
    "fuel",
    "compliance",
    "data-connector",
]

ExecutiveOverview = dict[str, Any]
