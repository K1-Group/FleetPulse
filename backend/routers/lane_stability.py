"""FleetPulse Lane Stability app endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from services.lakehouse_lane_stability_service import (
    MAX_WINDOW_DAYS,
    get_lane_stability_daily,
)


router = APIRouter()


@router.get("")
@router.get("/")
async def lane_stability_daily(
    window: int = Query(42, ge=1, le=MAX_WINDOW_DAYS),
    service: str | None = Query(default=None, min_length=1, max_length=128),
) -> dict[str, Any]:
    """Return read-only daily lane stability KPIs from the K1 lakehouse."""

    try:
        return get_lane_stability_daily(window=window, service=service)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        error = str(exc)
        status_code = 400 if "service_filter" in error else 503
        raise HTTPException(status_code=status_code, detail=error) from exc
