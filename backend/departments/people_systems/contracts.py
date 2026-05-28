"""People & Systems department contracts."""

from typing import Any

DEPARTMENT_ID = "people_systems"
SEAT_ID = "people_systems_manager"

DASHBOARD_TABS: list[str] = [
    "dashboard",
    "operating-system",
    "hr-recruiting",
    "reports",
]

CallAnalysisSnapshot = dict[str, Any]
