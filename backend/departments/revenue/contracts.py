"""Revenue department contracts."""

from typing import Any

DEPARTMENT_ID = "revenue"
SEAT_ID = "revenue_manager"

DASHBOARD_TABS: list[str] = [
    "dashboard",
    "control-tower",
    "finance",
    "operating-system",
    "stability",
]

RevenueProjection = dict[str, Any]
