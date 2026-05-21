"""Driver Workforce route-window API."""

from __future__ import annotations

from fastapi import APIRouter

from services.driver_workforce_service import get_driver_workforce_dataset


router = APIRouter()


@router.get("")
def driver_workforce() -> dict:
    return get_driver_workforce_dataset()
