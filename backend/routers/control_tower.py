"""Original Control Tower dashboard surfaces, restored as read-only projections."""

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from configs.xtra_lease import XtraLeaseIngestionConfig
from models import (
    ControlTowerAgentsResponse,
    ControlTowerAttentionResponse,
    ControlTowerCodexResponse,
    ControlTowerFinancialResponse,
    ControlTowerOverview,
    ControlTowerSeatKpiCoverageResponse,
    ControlTowerTrailerTrackingResponse,
    ControlTowerTrailersResponse,
)
from services import control_tower_service
from services.control_tower_seat_kpi_service import get_seat_kpi_coverage
from services.seat_kpi_feed_service import (
    get_seat_kpi_feed_status,
    import_seat_kpi_feed,
    list_seat_kpi_feed_statuses,
    validate_seat_kpi_feed_import_api_key,
)
from services.trailer_tracking_service import get_live_trailer_tracking
from services.xcelerator_event_feed_service import (
    import_xcelerator_events,
    validate_xcelerator_event_import_api_key,
    xcelerator_event_feed_status,
)
from services.xtra_lease_ingestion_service import (
    XtraLeaseConfigError,
    ingest_xtra_lease_emails,
    validate_ingestion_api_key,
)

router = APIRouter()


class XceleratorEventImportRequest(BaseModel):
    filename: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1)
    dry_run: bool = False


class SeatKpiFeedImportRequest(BaseModel):
    filename: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1)
    dry_run: bool = False


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


@router.get("/xcelerator/events/status")
def xcelerator_events_status() -> dict:
    return xcelerator_event_feed_status()


@router.post("/xcelerator/events/import")
def import_xcelerator_event_feed(
    request: XceleratorEventImportRequest,
    x_fleetpulse_xcelerator_key: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> dict:
    """Import scheduled Xcelerator event rows as read-only Tower evidence."""

    try:
        validate_xcelerator_event_import_api_key(x_fleetpulse_xcelerator_key or x_api_key)
        return import_xcelerator_events(
            request.content,
            filename=request.filename,
            dry_run=request.dry_run,
        ).as_dict()
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/seat-kpis", response_model=ControlTowerSeatKpiCoverageResponse)
def seat_kpis():
    return get_seat_kpi_coverage()


@router.get("/seat-kpis/feeds/status")
def seat_kpi_feed_statuses() -> dict:
    return list_seat_kpi_feed_statuses()


@router.get("/seat-kpis/feeds/{feed_key}/status")
def seat_kpi_feed_status(feed_key: str) -> dict:
    try:
        return get_seat_kpi_feed_status(feed_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/seat-kpis/feeds/{feed_key}/import")
def import_seat_kpi_feed_snapshot(
    feed_key: str,
    request: SeatKpiFeedImportRequest,
    x_fleetpulse_seat_kpi_key: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> dict:
    """Import scheduled source rows for missing seat KPI coverage."""

    try:
        validate_seat_kpi_feed_import_api_key(feed_key, x_fleetpulse_seat_kpi_key or x_api_key)
        return import_seat_kpi_feed(
            feed_key,
            request.content,
            filename=request.filename,
            dry_run=request.dry_run,
        ).as_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/agents", response_model=ControlTowerAgentsResponse)
def agents():
    return control_tower_service.get_agents()


@router.get("/codex", response_model=ControlTowerCodexResponse)
def codex():
    return control_tower_service.get_codex()
