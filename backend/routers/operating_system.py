"""K1 seat-based operating system endpoints.

These endpoints expose the org-chart deck as a read-only portal contract. They
do not mutate Xcelerator, Geotab, QuickBooks, SharePoint, or Time Doctor state.
"""

from fastapi import APIRouter, Depends, Header, HTTPException

from configs.operating_system import OperatingSystemRuntimeConfig
from models import (
    OperatingSystemConfigurationResponse,
    OperatingSystemDepartmentScorecardsResponse,
    OperatingSystemOrgChartResponse,
    OperatingSystemSeatResponse,
    OperatingSystemTaskKpiMatrixResponse,
)
from services import department_scorecard_service
from services import operating_system_service

router = APIRouter()


def validate_operating_system_api_key(
    x_fleetpulse_operating_system_key: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    config = OperatingSystemRuntimeConfig.from_env()
    if config.api_key_required and not config.api_key_configured:
        raise HTTPException(status_code=503, detail="operating_system_api_key_not_configured")
    provided_key = x_fleetpulse_operating_system_key or x_api_key
    if not config.is_authorized(provided_key):
        raise HTTPException(status_code=401, detail="invalid_operating_system_api_key")


@router.get(
    "/configuration",
    response_model=OperatingSystemConfigurationResponse,
    dependencies=[Depends(validate_operating_system_api_key)],
)
def configuration():
    return operating_system_service.get_configuration()


@router.get(
    "/org-chart",
    response_model=OperatingSystemOrgChartResponse,
    dependencies=[Depends(validate_operating_system_api_key)],
)
def org_chart():
    return operating_system_service.get_org_chart()


@router.get(
    "/department-scorecards",
    response_model=OperatingSystemDepartmentScorecardsResponse,
    dependencies=[Depends(validate_operating_system_api_key)],
)
def department_scorecards():
    return department_scorecard_service.get_department_scorecards()


@router.get(
    "/task-kpi-matrix",
    response_model=OperatingSystemTaskKpiMatrixResponse,
    dependencies=[Depends(validate_operating_system_api_key)],
)
def task_kpi_matrix():
    return operating_system_service.get_task_kpi_matrix()


@router.get(
    "/task-kpi-matrix/{seat_id}",
    response_model=OperatingSystemSeatResponse,
    dependencies=[Depends(validate_operating_system_api_key)],
)
def task_kpi_matrix_for_seat(seat_id: str):
    response = operating_system_service.get_task_kpi_for_seat(seat_id)
    if response is None:
        raise HTTPException(status_code=404, detail="seat_not_found")
    return response


@router.get(
    "/seats/{seat_id}",
    response_model=OperatingSystemSeatResponse,
    dependencies=[Depends(validate_operating_system_api_key)],
)
def seat_detail(seat_id: str):
    response = operating_system_service.get_task_kpi_for_seat(seat_id)
    if response is None:
        raise HTTPException(status_code=404, detail="seat_not_found")
    return response
