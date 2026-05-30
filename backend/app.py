"""FleetPulse — FastAPI main application."""

import logging
import os
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from http_cache import api_cache_control_header
from services.auth_session_service import build_auth_session
from services.entra_seat_access_service import tab_for_path

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


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _entra_auth_required() -> bool:
    return _env_bool("FLEETPULSE_ENTRA_AUTH_REQUIRED", False)


def _entra_seat_access_enforced() -> bool:
    return _env_bool("FLEETPULSE_ENTRA_SEAT_ACCESS_ENFORCED", False)


def _entra_principal_present(request: Request) -> bool:
    principal = request.headers.get("x-ms-client-principal", "").strip()
    idp = request.headers.get("x-ms-client-principal-idp", "").strip().lower()
    return bool(principal) and idp in {"aad", "azureactivedirectory"}


def _auth_exempt_path(path: str) -> bool:
    return path in {"/api/health", "/api/auth/session", "/api/auth/seat-access"} or path.startswith("/.auth")


@app.middleware("http")
async def enforce_entra_sso(request: Request, call_next):
    if not _entra_auth_required() or _auth_exempt_path(request.url.path):
        return await call_next(request)

    if _entra_principal_present(request):
        return await call_next(request)

    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=401,
            content={"detail": "Microsoft Entra SSO is required for FleetPulse."},
        )

    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    login_url = f"/.auth/login/aad?post_login_redirect_uri={quote(target, safe='')}"
    return RedirectResponse(login_url, status_code=302)


@app.middleware("http")
async def enforce_entra_seat_access(request: Request, call_next):
    if (
        not _entra_seat_access_enforced()
        or _auth_exempt_path(request.url.path)
        or not request.url.path.startswith("/api/")
    ):
        return await call_next(request)

    session = build_auth_session(request)
    access = session.get("seat_access") or {}
    tab = tab_for_path(request.url.path)

    if not session.get("authenticated"):
        return JSONResponse(
            status_code=401,
            content={"detail": "Microsoft Entra sign-in is required for FleetPulse seat access."},
        )

    if not access.get("authorized") or (tab and tab not in access.get("allowed_tabs", [])):
        return JSONResponse(
            status_code=403,
            content={
                "detail": "FleetPulse seat access denied.",
                "denied_reason": "tab_not_allowed_for_entra_seat" if tab else access.get("denied_reason"),
                "tab": tab,
            },
        )

    return await call_next(request)


@app.middleware("http")
async def add_dashboard_cache_headers(request: Request, call_next):
    response = await call_next(request)
    cache_control = api_cache_control_header(
        request.method,
        request.url.path,
        response.status_code,
    )
    if cache_control:
        response.headers["Cache-Control"] = cache_control
    return response


# Resilient router loading — skip any router with import errors
_ROUTERS = [
    ("auth", "/api/auth", ["Authentication"]),
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
    ("employee_workforce", "/api/employee-workforce", ["Employee Workforce"]),
    ("driver_workforce", "/api/driver-workforce", ["Driver Workforce"]),
    ("driver_compliance", "/api/driver-compliance", ["Driver Compliance"]),
    ("address_benchmarks", "/api/address-benchmarks", ["Address Benchmarks"]),
    ("hr_recruiting", "/api/hr-recruiting", ["HR Recruiting"]),
    ("hr_recruiting_powerbi", "/api/powerbi", ["Power BI"]),
    ("hr_call_analysis", "/api/hr-call-analysis", ["HR Call Analysis"]),
    ("department_call_analysis", "/api/department-call-analysis", ["Department Call Analysis"]),
    ("hr_call_analysis_powerbi", "/api/powerbi", ["Power BI"]),
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
