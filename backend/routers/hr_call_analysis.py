"""Read-only HR call-analysis endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from configs.hr_call_analysis import HrCallAnalysisConfig
from services.hr_call_analysis_service import (
    HrCallAnalysisConfigError,
    get_hr_call_analysis_dataset,
    hr_call_analysis_status,
    import_hr_call_analysis_snapshot,
    sync_hr_call_analysis_sharepoint_folder,
    validate_hr_call_analysis_import_api_key,
    validate_hr_call_analysis_sync_api_key,
)

router = APIRouter()


class HrCallAnalysisImportRequest(BaseModel):
    filename: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1)
    dry_run: bool = False


class HrCallAnalysisSyncRequest(BaseModel):
    dry_run: bool = False


@router.get("/dashboard")
async def hr_call_analysis_dashboard() -> dict[str, Any]:
    """Return dashboard-safe HR call analytics."""
    return await get_hr_call_analysis_dataset()


@router.get("/status")
async def hr_call_analysis_feed_status() -> dict[str, Any]:
    """Return safe readiness details for HR call-analysis feeds."""
    return hr_call_analysis_status()


@router.post("/import")
async def import_hr_call_analysis(
    request: HrCallAnalysisImportRequest,
    x_fleetpulse_hr_call_key: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    """Merge HR call-log or analysis-report evidence into FleetPulse state."""

    try:
        validate_hr_call_analysis_import_api_key(x_fleetpulse_hr_call_key or x_api_key)
        return import_hr_call_analysis_snapshot(
            request.content,
            filename=request.filename,
            dry_run=request.dry_run,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/sharepoint/sync")
async def sync_hr_call_analysis_sharepoint(
    request: HrCallAnalysisSyncRequest | None = None,
    x_fleetpulse_hr_call_key: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    """Pull HR call-analysis text reports from the configured SharePoint folder."""

    config = HrCallAnalysisConfig.from_env()
    try:
        validate_hr_call_analysis_sync_api_key(config, x_fleetpulse_hr_call_key or x_api_key)
        result = sync_hr_call_analysis_sharepoint_folder(
            config,
            dry_run=bool(request.dry_run if request else False),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except HrCallAnalysisConfigError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="hr_call_analysis_sharepoint_sync_failed") from exc
    return result.as_dict()
