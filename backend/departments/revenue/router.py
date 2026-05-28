"""Revenue department router facade."""

from routers.driver_workforce import router as driver_workforce_router
from routers.lane_stability import router as lane_stability_router

ROUTERS = [
    ("driver_workforce", "/api/driver-workforce", ["Driver Workforce"], driver_workforce_router),
    ("lane_stability", "/api/lane-stability", ["Lane Stability"], lane_stability_router),
]

__all__ = ["ROUTERS", "driver_workforce_router", "lane_stability_router"]
