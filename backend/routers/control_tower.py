"""Original Control Tower dashboard surfaces, restored as read-only projections."""

from fastapi import APIRouter

from models import (
    ControlTowerAgentsResponse,
    ControlTowerAttentionResponse,
    ControlTowerCodexResponse,
    ControlTowerFinancialResponse,
    ControlTowerOverview,
    ControlTowerTrailersResponse,
)
from services import control_tower_service

router = APIRouter()


@router.get("/overview", response_model=ControlTowerOverview)
def overview():
    return control_tower_service.get_overview()


@router.get("/attention", response_model=ControlTowerAttentionResponse)
def attention():
    return control_tower_service.get_attention()


@router.get("/trailers", response_model=ControlTowerTrailersResponse)
def trailers():
    return control_tower_service.get_trailers()


@router.get("/financial", response_model=ControlTowerFinancialResponse)
def financial():
    return control_tower_service.get_financial()


@router.get("/agents", response_model=ControlTowerAgentsResponse)
def agents():
    return control_tower_service.get_agents()


@router.get("/codex", response_model=ControlTowerCodexResponse)
def codex():
    return control_tower_service.get_codex()
