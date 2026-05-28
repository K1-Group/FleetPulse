"""Finance department router facade."""

from routers.fuel import router as fuel_router

ROUTERS = [
    ("fuel", "/api/fuel", ["Fuel Analytics"], fuel_router),
]

__all__ = ["ROUTERS", "fuel_router"]
