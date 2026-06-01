"""Read-only department call-analysis endpoints."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from configs.hr_call_analysis import HrCallAnalysisConfig
from services.hr_call_analysis_service import (
    HrCallAnalysisConfigError,
    department_call_analysis_status,
    get_department_call_analysis_dataset,
    import_hr_call_analysis_snapshot,
    sync_department_call_analysis_sharepoint_folders,
    validate_hr_call_analysis_import_api_key,
    validate_hr_call_analysis_sync_api_key,
)

router = APIRouter()


class DepartmentCallAnalysisImportRequest(BaseModel):
    department: str = Field(default="HR", max_length=80)
    filename: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1)
    dry_run: bool = False


class DepartmentCallAnalysisSyncRequest(BaseModel):
    dry_run: bool = False


@router.get("/dashboard")
async def department_call_analysis_dashboard(
    department: str | None = Query(default=None, max_length=80),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> dict[str, Any]:
    """Return dashboard-safe department call analytics."""

    return await get_department_call_analysis_dataset(
        department=department,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/status")
async def department_call_analysis_feed_status() -> dict[str, Any]:
    """Return safe readiness details for department call-analysis feeds."""

    return department_call_analysis_status()


@router.post("/import")
async def import_department_call_analysis(
    request: DepartmentCallAnalysisImportRequest,
    x_fleetpulse_hr_call_key: str | None = Header(default=None),
    x_fleetpulse_department_call_key: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    """Merge department call-log or analysis-report evidence into FleetPulse state."""

    try:
        validate_hr_call_analysis_import_api_key(
            x_fleetpulse_department_call_key or x_fleetpulse_hr_call_key or x_api_key
        )
        return import_hr_call_analysis_snapshot(
            request.content,
            filename=request.filename,
            department=request.department,
            dry_run=request.dry_run,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/sharepoint/sync")
async def sync_department_call_analysis_sharepoint(
    request: DepartmentCallAnalysisSyncRequest | None = None,
    x_fleetpulse_hr_call_key: str | None = Header(default=None),
    x_fleetpulse_department_call_key: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    """Pull configured department call-analysis text reports from SharePoint."""

    config = HrCallAnalysisConfig.from_env()
    try:
        validate_hr_call_analysis_sync_api_key(
            config,
            x_fleetpulse_department_call_key or x_fleetpulse_hr_call_key or x_api_key,
        )
        return sync_department_call_analysis_sharepoint_folders(
            config,
            dry_run=bool(request.dry_run if request else False),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except HrCallAnalysisConfigError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="department_call_analysis_sharepoint_sync_failed") from exc
