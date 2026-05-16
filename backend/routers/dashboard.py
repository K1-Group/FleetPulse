"""Fleet dashboard overview endpoints."""

from fastapi import APIRouter

from models import FleetOverview, LocationStats
from services.dashboard_validation_service import get_dashboard_validation_snapshot
from services.fleet_service import get_fleet_overview, get_location_stats

router = APIRouter()


@router.get("/overview", response_model=FleetOverview)
def overview():
    return get_fleet_overview()


@router.get("/locations", response_model=list[LocationStats])
def locations():
    return get_location_stats()


@router.get("/validation")
def validation():
    return get_dashboard_validation_snapshot()
