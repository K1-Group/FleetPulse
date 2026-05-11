"""Safety score endpoints."""

from fastapi import APIRouter, Query

from models import VehicleSafetyScore
from services.safety_service import get_safety_scores

router = APIRouter()


@router.get("/scores", response_model=list[VehicleSafetyScore])
def safety_scores(days: int = Query(7, ge=1, le=90)):
    return get_safety_scores(days=days)
