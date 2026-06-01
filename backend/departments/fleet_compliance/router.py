"""Fleet & Compliance department router facade."""

from routers.coaching import router as coaching_router
from routers.compliance import router as compliance_router
from routers.data_connector import router as data_connector_router
from routers.fuel import router as fuel_router
from routers.geofences import router as geofences_router
from routers.maintenance import router as maintenance_router
from routers.safety import router as safety_router
from routers.vehicles import router as vehicles_router

ROUTERS = [
    ("maintenance", "/api/maintenance", ["Predictive Maintenance"], maintenance_router),
    ("coaching", "/api/coaching", ["Driver Coaching"], coaching_router),
    ("geofences", "/api/geofences", ["Geofence Management"], geofences_router),
    ("fuel", "/api/fuel", ["Fuel Analytics"], fuel_router),
    ("compliance", "/api/compliance", ["Compliance & ELD"], compliance_router),
    ("vehicles", "/api/vehicles", ["Vehicles"], vehicles_router),
    ("safety", "/api/safety", ["Safety"], safety_router),
    ("data_connector", "/api/data-connector", ["Data Connector"], data_connector_router),
]

__all__ = [
    "ROUTERS",
    "coaching_router",
    "compliance_router",
    "data_connector_router",
    "fuel_router",
    "geofences_router",
    "maintenance_router",
    "safety_router",
    "vehicles_router",
]
