"""HR Recruiting department contracts."""

from typing import Any

DEPARTMENT_ID = "hr_recruiting"
SEAT_ID = "people_systems_manager"  # recruiting tabs share seat with people_systems today

DASHBOARD_TABS: list[str] = [
    "hr-recruiting",
]

RecruitingWorklistItem = dict[str, Any]
