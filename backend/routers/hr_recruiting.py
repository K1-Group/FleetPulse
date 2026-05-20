"""Read-only HR recruiting worklist monitor endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from services.hr_recruiting_service import (
    HrRecruitingConfig,
    get_hr_recruiting_dataset,
    import_hr_recruiting_snapshot,
    validate_hr_recruiting_import_api_key,
)

router = APIRouter()


class HrRecruitingImportRequest(BaseModel):
    filename: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1)
    dry_run: bool = False


@router.get("/worklist")
async def hr_recruiting_worklist() -> dict[str, Any]:
    """Return the HR worklist dashboard dataset without applicant PII."""
    return await get_hr_recruiting_dataset()


@router.get("/status")
async def hr_recruiting_status() -> dict[str, Any]:
    """Return safe source/configuration status for the HR recruiting feed."""
    return HrRecruitingConfig.from_env().safe_status()


@router.post("/import")
async def import_hr_recruiting_worklist(
    request: HrRecruitingImportRequest,
    x_fleetpulse_hr_key: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    """Replace the scheduled HR recruiting snapshot as read-only evidence."""

    try:
        validate_hr_recruiting_import_api_key(x_fleetpulse_hr_key or x_api_key)
        return import_hr_recruiting_snapshot(
            request.content,
            filename=request.filename,
            dry_run=request.dry_run,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
