"""Finance department contracts."""

from typing import Any

DEPARTMENT_ID = "finance"
SEAT_ID = "finance_controller"

DASHBOARD_TABS: list[str] = [
    "dashboard",
    "control-tower",
    "finance",
    "operating-system",
    "fuel",
]

FinancialSnapshot = dict[str, Any]
