"""Operations department contracts."""

from typing import Any

DEPARTMENT_ID = "operations"
SEAT_ID = "operations_manager"

DASHBOARD_TABS: list[str] = [
    "dashboard",
    "control-tower",
    "operating-system",
    "replay",
    "stability",
    "reports",
]

OperationsOverview = dict[str, Any]
