"""FleetPulse — FastAPI main application."""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("fleetpulse")


app = FastAPI(
    title="FleetPulse API",
    description="Multi-location fleet intelligence for K1 Logistics DFW",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Resilient router loading — skip any router with import errors
_ROUTERS = [
    ("dashboard", "/api/dashboard", ["Dashboard"]),
    ("vehicles", "/api/vehicles", ["Vehicles"]),
    ("safety", "/api/safety", ["Safety"]),
    ("gamification", "/api/gamification", ["Gamification"]),
    ("alerts", "/api/alerts", ["Alerts"]),
    ("monitor", "/api/monitor", ["Agentic Monitor"]),
    ("ai_chat", "/api/ai", ["AI Chat & Intelligence"]),
    ("coaching", "/api/coaching", ["Driver Coaching"]),
    ("maintenance", "/api/maintenance", ["Predictive Maintenance"]),
    ("trips", "/api/trips", ["Route Replay"]),
    ("reports", "/api/reports", ["Fleet Reports"]),
    ("geofences", "/api/geofences", ["Geofence Management"]),
    ("fuel", "/api/fuel", ["Fuel Analytics"]),
    ("compliance", "/api/compliance", ["Compliance & ELD"]),
    ("control_tower", "/api/control-tower", ["Control Tower"]),
    ("operating_system", "/api/operating-system", ["K1 Operating System"]),
    ("data_connector", "/api/data-connector", ["Data Connector"]),
    ("driver_workforce", "/api/driver-workforce", ["Driver Workforce"]),
    ("hr_recruiting", "/api/hr-recruiting", ["HR Recruiting"]),
    ("hr_recruiting_powerbi", "/api/powerbi", ["Power BI"]),
    ("powerbi", "/api/powerbi", ["Power BI"]),
    ("lane_stability", "/api/lane-stability", ["Lane Stability"]),
    ("zapier", "/api/zapier", ["Zapier"]),
]
for _name, _prefix, _tags in _ROUTERS:
    try:
        _mod = __import__(f"routers.{_name}", fromlist=["router"])
        app.include_router(_mod.router, prefix=_prefix, tags=_tags)
        logger.info(f"Router loaded: {_name}")
    except Exception as exc:
        logger.warning(f"Skipped router {_name}: {exc}")

@app.on_event("startup")
async def startup_event():
    monitor_enabled = os.getenv("FLEETPULSE_MONITOR_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not monitor_enabled:
        logger.info("Monitor startup skipped: FLEETPULSE_MONITOR_ENABLED is not true")
        return
    try:
        from services.monitor_service import start_monitor
        start_monitor()
        logger.info("Monitor started successfully")
    except Exception as e:
        logger.warning(f"Monitor startup skipped: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    try:
        from services.monitor_service import stop_monitor
        stop_monitor()
    except Exception as e:
        logger.warning(f"Monitor shutdown skipped: {e}")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "FleetPulse"}
