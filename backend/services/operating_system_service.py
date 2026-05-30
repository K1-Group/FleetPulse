"""Read-only service for the K1 seat-based operating system portal contract."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from configs.operating_system import (
    ACCESS_BUNDLE,
    FUNCTIONAL_SEATS,
    MANAGEMENT_TREE,
    MANAGER_SEATS,
    ORG_CHART_SOURCE,
    OperatingSystemRuntimeConfig,
    PORTAL_WORKFLOW,
    REVENUE_TARGETS,
    SCORECARD_WEIGHTS,
    SOURCE_BOUNDARIES,
)
from models import (
    OperatingSystemConfigurationResponse,
    OperatingSystemManagerNode,
    OperatingSystemOrgChartResponse,
    OperatingSystemPortalStep,
    OperatingSystemSeatContract,
    OperatingSystemSeatResponse,
    OperatingSystemSourceBoundary,
    OperatingSystemTaskKpiMatrixResponse,
)

ENDPOINT_CONTRACT = [
    "GET /api/operating-system/org-chart",
    "GET /api/operating-system/department-scorecards",
    "GET /api/operating-system/task-kpi-matrix",
    "GET /api/operating-system/task-kpi-matrix/{seat_id}",
    "GET /api/operating-system/seats/{seat_id}",
    "GET /api/operating-system/configuration",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seat_from_config(item: dict, seat_type: str, managed_seat_ids: Iterable[str] = ()) -> OperatingSystemSeatContract:
    return OperatingSystemSeatContract(
        seat_id=item["seat_id"],
        label=item["label"],
        seat_type=seat_type,
        primary_score=item["primary_score"],
        entity_scope=item["entity_scope"],
        source_authorities=list(item["source_authorities"]),
        manager_seat_id=item.get("manager_seat_id"),
        managed_seat_ids=list(managed_seat_ids),
        daily_work=list(item["daily_work"]),
        targets=dict(item["targets"]),
        access_bundle=list(ACCESS_BUNDLE),
        scorecard_weights=dict(SCORECARD_WEIGHTS),
    )


def _manager_children() -> dict[str, list[str]]:
    return {
        node["manager_seat_id"]: list(node["functional_seat_ids"])
        for node in MANAGEMENT_TREE
    }


def get_seats() -> list[OperatingSystemSeatContract]:
    manager_children = _manager_children()
    manager_seats = [
        _seat_from_config(item, "accountability", manager_children.get(item["seat_id"], []))
        for item in MANAGER_SEATS
    ]
    functional_seats = [
        _seat_from_config(item, "functional")
        for item in FUNCTIONAL_SEATS
    ]
    return manager_seats + functional_seats


def get_seat(seat_id: str) -> OperatingSystemSeatContract | None:
    normalized = seat_id.strip().lower()
    for seat in get_seats():
        if seat.seat_id == normalized:
            return seat
    return None


def get_source_boundaries() -> list[OperatingSystemSourceBoundary]:
    return [OperatingSystemSourceBoundary(**boundary) for boundary in SOURCE_BOUNDARIES]


def get_portal_workflow() -> list[OperatingSystemPortalStep]:
    return [OperatingSystemPortalStep(**step) for step in PORTAL_WORKFLOW]


def get_management_tree() -> list[OperatingSystemManagerNode]:
    seat_map = {seat.seat_id: seat for seat in get_seats()}
    nodes: list[OperatingSystemManagerNode] = []
    for node in MANAGEMENT_TREE:
        manager = seat_map[node["manager_seat_id"]]
        functional_ids = list(node["functional_seat_ids"])
        nodes.append(
            OperatingSystemManagerNode(
                manager_seat_id=manager.seat_id,
                manager_label=manager.label,
                functional_seat_ids=functional_ids,
                functional_seats=[seat_map[seat_id] for seat_id in functional_ids],
            )
        )
    return nodes


def get_org_chart() -> OperatingSystemOrgChartResponse:
    seats = get_seats()
    return OperatingSystemOrgChartResponse(
        generated_at=_now(),
        source_document=dict(ORG_CHART_SOURCE),
        targets=dict(REVENUE_TARGETS),
        total_seats=len(seats),
        accountability_seats=sum(1 for seat in seats if seat.seat_type == "accountability"),
        functional_seats=sum(1 for seat in seats if seat.seat_type == "functional"),
        seats=seats,
        management_tree=get_management_tree(),
        source_boundaries=get_source_boundaries(),
        portal_workflow=get_portal_workflow(),
        endpoint_contract=list(ENDPOINT_CONTRACT),
    )


def get_task_kpi_matrix() -> OperatingSystemTaskKpiMatrixResponse:
    return OperatingSystemTaskKpiMatrixResponse(
        generated_at=_now(),
        seats=get_seats(),
        scorecard_weights=dict(SCORECARD_WEIGHTS),
    )


def get_task_kpi_for_seat(seat_id: str) -> OperatingSystemSeatResponse | None:
    seat = get_seat(seat_id)
    if seat is None:
        return None
    return OperatingSystemSeatResponse(
        generated_at=_now(),
        seat=seat,
        source_boundaries=get_source_boundaries(),
    )


def get_configuration() -> OperatingSystemConfigurationResponse:
    config = OperatingSystemRuntimeConfig.from_env()
    return OperatingSystemConfigurationResponse(
        generated_at=_now(),
        api_key_required=config.api_key_required,
        auth_headers=["X-FleetPulse-Operating-System-Key", "X-API-Key"],
        items=config.status_items(),
        source_boundaries=get_source_boundaries(),
    )
