"""Read-only HR recruiting worklist monitor endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from services.hr_recruiting_service import HrRecruitingConfig, get_hr_recruiting_dataset

router = APIRouter()


@router.get("/worklist")
async def hr_recruiting_worklist() -> dict[str, Any]:
    """Return the HR worklist dashboard dataset without applicant PII."""
    return await get_hr_recruiting_dataset()


@router.get("/status")
async def hr_recruiting_status() -> dict[str, Any]:
    """Return safe source/configuration status for the HR recruiting feed."""
    return HrRecruitingConfig.from_env().safe_status()
