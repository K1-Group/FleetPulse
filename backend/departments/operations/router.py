"""Operations department router facade."""

from routers.control_tower import router as control_tower_router
from routers.lane_stability import router as lane_stability_router
from routers.operating_system import router as operating_system_router
from routers.reports import router as reports_router
from routers.trips import router as trips_router

ROUTERS = [
    ("control_tower", "/api/control-tower", ["Control Tower"], control_tower_router),
    ("operating_system", "/api/operating-system", ["K1 Operating System"], operating_system_router),
    ("trips", "/api/trips", ["Route Replay"], trips_router),
    ("reports", "/api/reports", ["Fleet Reports"], reports_router),
    ("lane_stability", "/api/lane-stability", ["Lane Stability"], lane_stability_router),
]

__all__ = [
    "ROUTERS",
    "control_tower_router",
    "operating_system_router",
    "trips_router",
    "reports_router",
    "lane_stability_router",
]
