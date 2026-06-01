"""Employee Workforce API backed by read-only Time Doctor activity evidence."""

from __future__ import annotations

from fastapi import APIRouter

from services.employee_workforce_service import get_employee_workforce_dataset


router = APIRouter()


@router.get("")
def employee_workforce() -> dict:
    return get_employee_workforce_dataset()
