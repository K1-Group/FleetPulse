"""HR Recruiting department router facade."""

from routers.hr_recruiting import router as hr_recruiting_router
from routers.hr_recruiting_powerbi import router as hr_recruiting_powerbi_router

ROUTERS = [
    ("hr_recruiting", "/api/hr-recruiting", ["HR Recruiting"], hr_recruiting_router),
    ("hr_recruiting_powerbi", "/api/powerbi", ["Power BI"], hr_recruiting_powerbi_router),
]

__all__ = ["ROUTERS", "hr_recruiting_router", "hr_recruiting_powerbi_router"]
