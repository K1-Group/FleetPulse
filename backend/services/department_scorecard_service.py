"""Read-only department scorecards derived from the fixed seat contract."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from configs.operating_system import SCORECARD_WEIGHTS
from models import (
    ControlTowerSeatKpiItem,
    ControlTowerStatus,
    OperatingSystemDepartmentScorecard,
    OperatingSystemDepartmentScorecardSummary,
    OperatingSystemDepartmentScorecardsResponse,
    OperatingSystemSeatContract,
)
from services.control_tower_seat_kpi_service import get_seat_kpi_coverage
from services.operating_system_service import get_management_tree, get_seats


DEPARTMENT_LABELS: dict[str, str] = {
    "revenue_manager": "Revenue",
    "operations_manager": "Operations",
    "finance_controller": "Finance",
    "fleet_compliance_manager": "Fleet & Compliance",
    "people_systems_manager": "People & Systems",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _scorecard_summary(kpis: list[ControlTowerSeatKpiItem]) -> OperatingSystemDepartmentScorecardSummary:
    counts = Counter(item.status.value for item in kpis)
    covered = counts[ControlTowerStatus.HEALTHY.value] + counts[ControlTowerStatus.WARNING.value]
    total = len(kpis)
    return OperatingSystemDepartmentScorecardSummary(
        total=total,
        healthy=counts[ControlTowerStatus.HEALTHY.value],
        warning=counts[ControlTowerStatus.WARNING.value],
        awaiting_feed=counts[ControlTowerStatus.AWAITING_FEED.value],
        unavailable=counts[ControlTowerStatus.UNAVAILABLE.value],
        coverage_pct=round((covered / total) * 100, 1) if total else 0,
    )


def _department_source_authorities(manager: OperatingSystemSeatContract) -> list[str]:
    authorities: list[str] = []
    for authority in manager.source_authorities:
        if authority not in authorities:
            authorities.append(authority)
    return authorities


def get_department_scorecards() -> OperatingSystemDepartmentScorecardsResponse:
    """Return one read-only scorecard per fixed manager department."""

    seats = {seat.seat_id: seat for seat in get_seats()}
    kpi_coverage = get_seat_kpi_coverage()
    kpis_by_manager: dict[str, list[ControlTowerSeatKpiItem]] = {}
    for item in kpi_coverage.kpis:
        kpis_by_manager.setdefault(item.seat_id, []).append(item)

    scorecards: list[OperatingSystemDepartmentScorecard] = []
    for node in get_management_tree():
        if node.manager_seat_id == "executive_command":
            continue
        manager = seats[node.manager_seat_id]
        department_label = DEPARTMENT_LABELS.get(node.manager_seat_id, manager.label.replace(" Seat", ""))
        kpis = kpis_by_manager.get(node.manager_seat_id, [])
        scorecards.append(
            OperatingSystemDepartmentScorecard(
                department_id=node.manager_seat_id,
                department_label=department_label,
                manager_seat_id=node.manager_seat_id,
                manager_label=manager.label,
                entity_scope=manager.entity_scope,
                source_authorities=_department_source_authorities(manager),
                scorecard_weights=dict(SCORECARD_WEIGHTS),
                managed_seats=node.functional_seats,
                kpi_summary=_scorecard_summary(kpis),
                kpis=kpis,
                source_message=(
                    "Scorecard is a read-only department contract. FleetPulse shows source "
                    "coverage and configured KPI targets only; source systems remain authoritative "
                    "for actual performance values."
                ),
            )
        )

    return OperatingSystemDepartmentScorecardsResponse(
        generated_at=_now(),
        scorecard_weights=dict(SCORECARD_WEIGHTS),
        departments=scorecards,
    )
