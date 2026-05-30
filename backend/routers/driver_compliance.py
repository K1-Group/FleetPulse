"""Driver Compliance document-expiration API foundation."""

from __future__ import annotations

from fastapi import APIRouter

from services.driver_compliance_service import get_driver_compliance_dataset


router = APIRouter()


@router.get("")
def driver_compliance() -> dict:
    return get_driver_compliance_dataset()
