"""Original Control Tower dashboard surfaces, restored as read-only projections."""

import os

from fastapi import APIRouter, Header, HTTPException

from configs.xtra_lease import XtraLeaseIngestionConfig
from models import (
    ControlTowerAgentsResponse,
    ControlTowerAttentionResponse,
    ControlTowerCodexResponse,
    ControlTowerFinancialResponse,
    ControlTowerOverview,
    ControlTowerTrailerTrackingResponse,
    ControlTowerTrailersResponse,
)
from services import control_tower_service
from services.trailer_tracking_service import get_live_trailer_tracking
from services.xcelerator_gross_margin_service import (
    get_gross_margin_rebuild_status,
    start_gross_margin_summary_rebuild,
)
from services.xtra_lease_ingestion_service import (
    XtraLeaseConfigError,
    ingest_xtra_lease_emails,
    validate_ingestion_api_key,
)

router = APIRouter()


def _validate_control_tower_admin_key(value: str | None) -> None:
    expected = (
        os.getenv("FLEETPULSE_CONTROL_TOWER_ADMIN_KEY", "").strip()
        or os.getenv("FLEETPULSE_XCELERATOR_GROSS_MARGIN_REBUILD_KEY", "").strip()
    )
    if not expected:
        raise HTTPException(status_code=409, detail="control_tower_admin_key_not_configured")
    if value != expected:
        raise HTTPException(status_code=401, detail="invalid_control_tower_admin_key")


@router.get("/overview", response_model=ControlTowerOverview)
def overview():
    return control_tower_service.get_overview()


@router.get("/attention", response_model=ControlTowerAttentionResponse)
def attention():
    return control_tower_service.get_attention()


@router.get("/trailers", response_model=ControlTowerTrailersResponse)
def trailers():
    return control_tower_service.get_trailers()


@router.get("/trailers/live", response_model=ControlTowerTrailerTrackingResponse)
def live_trailer_tracking():
    return get_live_trailer_tracking()


@router.post("/trailers/xtra/ingest")
def ingest_xtra_trailer_feed(
    x_fleetpulse_xtra_key: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> dict:
    """Pull read-only XTRA geofence emails from the configured Outlook folder."""

    config = XtraLeaseIngestionConfig.from_env()
    try:
        validate_ingestion_api_key(config, x_fleetpulse_xtra_key or x_api_key)
        return ingest_xtra_lease_emails(config).as_dict()
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except XtraLeaseConfigError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="xtra_ingestion_failed") from exc


@router.get("/financial", response_model=ControlTowerFinancialResponse)
def financial():
    return control_tower_service.get_financial()


@router.get("/financial/gross-margin/rebuild")
def gross_margin_rebuild_status(
    x_fleetpulse_admin_key: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
):
    _validate_control_tower_admin_key(x_fleetpulse_admin_key or x_api_key)
    return get_gross_margin_rebuild_status()


@router.post("/financial/gross-margin/rebuild")
def rebuild_gross_margin_summary(
    start: str | None = None,
    end: str | None = None,
    x_fleetpulse_admin_key: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
):
    _validate_control_tower_admin_key(x_fleetpulse_admin_key or x_api_key)
    return start_gross_margin_summary_rebuild(start=start, end=end)


@router.get("/agents", response_model=ControlTowerAgentsResponse)
def agents():
    return control_tower_service.get_agents()


@router.get("/codex", response_model=ControlTowerCodexResponse)
def codex():
    return control_tower_service.get_codex()
