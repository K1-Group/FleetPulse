"""People & Systems department router facade."""

from routers.department_call_analysis import router as department_call_analysis_router
from routers.hr_call_analysis import router as hr_call_analysis_router
from routers.hr_call_analysis_powerbi import router as hr_call_analysis_powerbi_router

ROUTERS = [
    ("department_call_analysis", "/api/department-call-analysis", ["Department Call Analysis"], department_call_analysis_router),
    ("hr_call_analysis", "/api/hr-call-analysis", ["HR Call Analysis"], hr_call_analysis_router),
    ("hr_call_analysis_powerbi", "/api/powerbi", ["Power BI"], hr_call_analysis_powerbi_router),
]

__all__ = [
    "ROUTERS",
    "department_call_analysis_router",
    "hr_call_analysis_router",
    "hr_call_analysis_powerbi_router",
]
