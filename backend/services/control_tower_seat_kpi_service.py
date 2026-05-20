"""Read-only seat KPI coverage for Control Tower.

This service maps the fixed-seat operating-system contract to FleetPulse KPI
routes. It reports what is live, partial, or still missing without fabricating
values from systems that are not connected.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

from models import (
    ControlTowerFeedStatus,
    ControlTowerSeatKpiCoverageResponse,
    ControlTowerSeatKpiCoverageSummary,
    ControlTowerSeatKpiItem,
    ControlTowerStatus,
)
from services.operating_system_service import get_seats


@dataclass(frozen=True)
class SeatKpiContract:
    key: str
    label: str
    seat_id: str
    target: str
    source_authority: str
    owner_action: str
    source_route: str | None = None
    base_status: ControlTowerStatus = ControlTowerStatus.AWAITING_FEED
    required_config: tuple[str, ...] = ()
    blocker: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _env_present(name: str) -> bool:
    if name.endswith("*"):
        prefix = name[:-1]
        return any(value for key, value in os.environ.items() if key.startswith(prefix) and value.strip())
    return bool(os.getenv(name, "").strip())


def _config_item_present(item: str) -> bool:
    alternatives = [part.strip() for part in item.split("|") if part.strip()]
    return any(_env_present(part) for part in alternatives)


def _missing_config(required_config: tuple[str, ...]) -> list[str]:
    return [item.replace("|", " or ") for item in required_config if not _config_item_present(item)]


CATALOG: tuple[SeatKpiContract, ...] = (
    SeatKpiContract(
        key="pipeline_coverage",
        label="Pipeline Coverage",
        seat_id="revenue_manager",
        target=">= 3x next-60-day sales target",
        source_authority="K1 Group LLC / Xcelerator CRM",
        source_route=None,
        blocker="xcelerator_crm_pipeline_feed_missing",
        required_config=("XCELERATOR_API_BASE_URL",),
        owner_action="Expose read-only opportunity pipeline by close window and stage.",
    ),
    SeatKpiContract(
        key="quote_margin_compliance",
        label="Quote Margin Compliance",
        seat_id="revenue_manager",
        target=">= 98%",
        source_authority="K1 Group LLC / Xcelerator pricing + SharePoint approvals",
        source_route=None,
        blocker="quote_margin_rule_feed_missing",
        required_config=("XCELERATOR_API_BASE_URL", "SHAREPOINT_SITE_ID"),
        owner_action="Publish quote, rate-rule, and approval-reference feed.",
    ),
    SeatKpiContract(
        key="booked_revenue",
        label="Booked Revenue",
        seat_id="revenue_manager",
        target=">= managed monthly target",
        source_authority="K1 Group LLC / Xcelerator ReviewOrders",
        source_route="/api/fuel/entity-margin",
        base_status=ControlTowerStatus.WARNING,
        required_config=("FLEETPULSE_XCELERATOR_WAREHOUSE_SQL_*|FLEETPULSE_XCELERATOR_REVIEW_ORDERS_STATE_PATH",),
        blocker="entity_margin_feed_partial_or_missing",
        owner_action="Keep Fabric Warehouse SQL preferred; local ReviewOrders import is fallback evidence.",
    ),
    SeatKpiContract(
        key="win_rate",
        label="Win Rate",
        seat_id="revenue_manager",
        target=">= 25%",
        source_authority="K1 Group LLC / Xcelerator opportunity stages",
        source_route=None,
        blocker="opportunity_stage_history_missing",
        required_config=("XCELERATOR_API_BASE_URL",),
        owner_action="Add closed-won and closed-lost opportunity history feed.",
    ),
    SeatKpiContract(
        key="revenue_expansion",
        label="Revenue Expansion",
        seat_id="revenue_manager",
        target=">= $50,000 monthly",
        source_authority="K1 Group LLC / Xcelerator account revenue history",
        source_route=None,
        blocker="account_expansion_feed_missing",
        required_config=("XCELERATOR_API_BASE_URL",),
        owner_action="Add account-level month-over-month revenue expansion rollup.",
    ),
    SeatKpiContract(
        key="lane_stability",
        label="Lane Stability",
        seat_id="operations_manager",
        target=">= 80% stable coverage",
        source_authority="K1 Group LLC / Fabric lakehouse lane_stability_daily_kpi",
        source_route="/api/lane-stability?window=364",
        base_status=ControlTowerStatus.HEALTHY,
        required_config=("LAKEHOUSE_SQL_SERVER|FLEETPULSE_XCELERATOR_WAREHOUSE_SQL_*",),
        blocker="lakehouse_lane_stability_feed_missing",
        owner_action="Keep daily lakehouse refresh healthy and monitor critical lanes.",
    ),
    SeatKpiContract(
        key="active_load_exception_aging",
        label="Active Load Exception Aging",
        seat_id="operations_manager",
        target="<= 5% active load exception rate",
        source_authority="K1 Group LLC / Xcelerator event feed",
        source_route="/api/control-tower/attention",
        base_status=ControlTowerStatus.WARNING,
        required_config=("FLEETPULSE_XCELERATOR_EVENT_FEED_URL",),
        blocker="xcelerator_exception_event_feed_partial",
        owner_action="Publish route/load exception events with created-at and resolved-at timestamps.",
    ),
    SeatKpiContract(
        key="on_time_dispatch",
        label="On-Time Dispatch",
        seat_id="operations_manager",
        target=">= 96%",
        source_authority="K1 Group LLC / Xcelerator dispatch lifecycle",
        source_route=None,
        blocker="dispatch_timestamp_feed_missing",
        required_config=("XCELERATOR_API_BASE_URL",),
        owner_action="Add ready-to-dispatch, assigned, accepted, and late-dispatch timestamps.",
    ),
    SeatKpiContract(
        key="pickup_delivery_otd",
        label="Pickup / Delivery OTD",
        seat_id="operations_manager",
        target=">= 95%",
        source_authority="K1 Group LLC / Xcelerator ReviewOrders actuals",
        source_route="/api/fuel/delivery-center-performance?days=370",
        base_status=ControlTowerStatus.WARNING,
        required_config=("FLEETPULSE_XCELERATOR_WAREHOUSE_SQL_*|FLEETPULSE_XCELERATOR_REVIEW_ORDERS_STATE_PATH",),
        blocker="delivery_center_performance_feed_partial_or_missing",
        owner_action="Confirm target/actual timestamp coverage by delivery center.",
    ),
    SeatKpiContract(
        key="uncovered_load_board",
        label="Uncovered Load Board",
        seat_id="operations_manager",
        target="100% covered active board",
        source_authority="K1 Group LLC / Xcelerator active load board",
        source_route=None,
        blocker="active_load_board_feed_missing",
        required_config=("XCELERATOR_API_BASE_URL",),
        owner_action="Expose active loads with coverage status and tender aging.",
    ),
    SeatKpiContract(
        key="ap_aging",
        label="AP Aging",
        seat_id="finance_controller",
        target="<= 10% over 30 days",
        source_authority="K1 Group LLC / QuickBooks Online",
        source_route="/api/control-tower/financial",
        base_status=ControlTowerStatus.WARNING,
        required_config=("FLEETPULSE_QBO_FINANCIAL_FEED_URL|FLEETPULSE_QBO_FINANCIAL_FEED_PATH",),
        blocker="qbo_ap_snapshot_partial_or_missing",
        owner_action="Connect scheduled QBO AP aging snapshot or state-file feed.",
    ),
    SeatKpiContract(
        key="ar_over_30",
        label="AR Over 30",
        seat_id="finance_controller",
        target="<= 15% of AR",
        source_authority="K1 Group LLC / QuickBooks Online",
        source_route="/api/control-tower/financial",
        base_status=ControlTowerStatus.WARNING,
        required_config=("FLEETPULSE_QBO_FINANCIAL_FEED_URL|FLEETPULSE_QBO_FINANCIAL_FEED_PATH",),
        blocker="qbo_ar_snapshot_partial_or_missing",
        owner_action="Connect scheduled QBO AR aging snapshot or state-file feed.",
    ),
    SeatKpiContract(
        key="billing_exception_aging",
        label="Billing Exception Aging",
        seat_id="finance_controller",
        target="<= 5% over 48h",
        source_authority="K1 Group LLC / Xcelerator + SharePoint billing packets",
        source_route=None,
        blocker="billing_packet_exception_feed_missing",
        required_config=("XCELERATOR_API_BASE_URL", "SHAREPOINT_SITE_ID"),
        owner_action="Publish delivered-not-invoice-ready queue with POD/billing packet blockers.",
    ),
    SeatKpiContract(
        key="driver_pay_exceptions",
        label="Driver-Pay Exceptions",
        seat_id="finance_controller",
        target="<= 1 business day resolution",
        source_authority="K1 Group LLC / Xcelerator settlements",
        source_route="/api/fuel/xcelerator/review-orders/summary",
        base_status=ControlTowerStatus.WARNING,
        required_config=("FLEETPULSE_XCELERATOR_WAREHOUSE_SQL_*|FLEETPULSE_XCELERATOR_REVIEW_ORDERS_STATE_PATH",),
        blocker="driver_pay_exception_detail_missing",
        owner_action="Extend ReviewOrders/settlement feed with exception status and age.",
    ),
    SeatKpiContract(
        key="weekly_close_variance",
        label="Weekly Close Variance",
        seat_id="finance_controller",
        target="closed within tolerance",
        source_authority="K1 Group LLC / QuickBooks + SharePoint close ledger",
        source_route=None,
        blocker="weekly_close_ledger_missing",
        required_config=("FLEETPULSE_QBO_FINANCIAL_FEED_URL", "SHAREPOINT_SITE_ID"),
        owner_action="Create SharePoint weekly close ledger with QBO reconciliation variance.",
    ),
    SeatKpiContract(
        key="truck_availability",
        label="Truck Availability",
        seat_id="fleet_compliance_manager",
        target=">= 90%",
        source_authority="K1 Logistics Inc / Geotab",
        source_route="/api/dashboard/overview",
        base_status=ControlTowerStatus.HEALTHY,
        required_config=("GEOTAB_SERVER", "GEOTAB_USERNAME", "GEOTAB_PASSWORD", "GEOTAB_DATABASE"),
        blocker="geotab_credentials_missing",
        owner_action="Use scoped active/offline Geotab vehicle status as the availability numerator.",
    ),
    SeatKpiContract(
        key="pm_compliance",
        label="PM Compliance",
        seat_id="fleet_compliance_manager",
        target="100%",
        source_authority="K1 Logistics Inc / Geotab + SharePoint maintenance evidence",
        source_route="/api/maintenance/predictions",
        base_status=ControlTowerStatus.WARNING,
        required_config=("GEOTAB_SERVER", "SHAREPOINT_SITE_ID"),
        blocker="maintenance_completion_evidence_partial",
        owner_action="Connect completed-date/status evidence for PM work orders.",
    ),
    SeatKpiContract(
        key="critical_faults_open",
        label="Critical Faults Open",
        seat_id="fleet_compliance_manager",
        target="0 past due",
        source_authority="K1 Logistics Inc / Geotab",
        source_route="/api/maintenance/urgent",
        base_status=ControlTowerStatus.WARNING,
        required_config=("GEOTAB_SERVER", "GEOTAB_USERNAME", "GEOTAB_PASSWORD", "GEOTAB_DATABASE"),
        blocker="geotab_fault_feed_partial_or_missing",
        owner_action="Route critical fault rows to named maintenance owners.",
    ),
    SeatKpiContract(
        key="mttr",
        label="Mean Time To Repair",
        seat_id="fleet_compliance_manager",
        target="<= 4 hours",
        source_authority="K1 Logistics Inc / Geotab + SharePoint work orders",
        source_route=None,
        blocker="maintenance_completed_timestamps_missing",
        required_config=("GEOTAB_SERVER", "SHAREPOINT_SITE_ID"),
        owner_action="Add assigned-to, opened-at, completed-at, and completed-status work-order feed.",
    ),
    SeatKpiContract(
        key="safety_coaching_closure",
        label="Safety / Coaching Closure",
        seat_id="fleet_compliance_manager",
        target="100%",
        source_authority="K1 Logistics Inc / Geotab coaching + SharePoint acknowledgements",
        source_route="/api/coaching/reports",
        base_status=ControlTowerStatus.WARNING,
        required_config=("GEOTAB_SERVER", "SHAREPOINT_SITE_ID"),
        blocker="coaching_acknowledgement_feed_partial",
        owner_action="Connect coaching task closure and acknowledgement evidence.",
    ),
    SeatKpiContract(
        key="seat_fill_rate",
        label="Seat Fill Rate",
        seat_id="people_systems_manager",
        target=">= 95%",
        source_authority="K1 Workforce Intelligence / SharePoint Seat_Assignments",
        source_route="/api/operating-system/task-kpi-matrix",
        base_status=ControlTowerStatus.WARNING,
        required_config=("SHAREPOINT_SITE_ID",),
        blocker="sharepoint_seat_assignments_feed_missing",
        owner_action="Sync SharePoint Seat_Assignments as the seat authority.",
    ),
    SeatKpiContract(
        key="training_completion",
        label="Training Completion",
        seat_id="people_systems_manager",
        target="100%",
        source_authority="K1 Workforce Intelligence / SharePoint Training_History",
        source_route=None,
        blocker="training_history_feed_missing",
        required_config=("SHAREPOINT_SITE_ID",),
        owner_action="Publish Training_History completion by employee and seat.",
    ),
    SeatKpiContract(
        key="access_lifecycle_sla",
        label="Access Lifecycle SLA",
        seat_id="people_systems_manager",
        target="<= 4 hours",
        source_authority="Microsoft 365 / SharePoint access ledger",
        source_route=None,
        blocker="access_grant_revoke_ledger_missing",
        required_config=("SHAREPOINT_SITE_ID",),
        owner_action="Log grant/revoke request, approval, completion, and elapsed time.",
    ),
    SeatKpiContract(
        key="integration_uptime",
        label="Integration Uptime",
        seat_id="people_systems_manager",
        target=">= 99%",
        source_authority="FleetPulse monitor + dashboard validation",
        source_route="/api/dashboard/validation",
        base_status=ControlTowerStatus.HEALTHY,
        required_config=(),
        owner_action="Use dashboard validation and monitor probes as the integration uptime evidence.",
    ),
    SeatKpiContract(
        key="failed_job_aging",
        label="Failed Job Aging",
        seat_id="people_systems_manager",
        target="<= 4 hours",
        source_authority="FleetPulse monitor alerts",
        source_route="/api/monitor/alerts",
        base_status=ControlTowerStatus.WARNING,
        required_config=("FLEETPULSE_MONITOR_ENABLED",),
        blocker="monitor_alert_resolution_state_partial",
        owner_action="Track failed job first-seen, owner, last retry, and resolved-at state.",
    ),
)


def _status_for(contract: SeatKpiContract) -> tuple[ControlTowerStatus, str | None, list[str]]:
    missing = _missing_config(contract.required_config)
    if contract.source_route is None:
        return ControlTowerStatus.AWAITING_FEED, contract.blocker or "fleetpulse_route_not_implemented", missing
    if missing:
        return ControlTowerStatus.AWAITING_FEED, contract.blocker or "required_config_missing", missing
    return contract.base_status, contract.blocker if contract.base_status != ControlTowerStatus.HEALTHY else None, []


def get_seat_kpi_coverage() -> ControlTowerSeatKpiCoverageResponse:
    """Return missing/live KPI coverage for the fixed-seat operating model."""

    seats = {seat.seat_id: seat for seat in get_seats()}
    items: list[ControlTowerSeatKpiItem] = []
    for contract in CATALOG:
        seat = seats.get(contract.seat_id)
        status, blocker, missing = _status_for(contract)
        items.append(
            ControlTowerSeatKpiItem(
                key=contract.key,
                label=contract.label,
                seat_id=contract.seat_id,
                seat_label=seat.label if seat else contract.seat_id.replace("_", " ").title(),
                manager_seat_id=seat.manager_seat_id if seat else None,
                target=contract.target,
                source_authority=contract.source_authority,
                source_route=contract.source_route,
                status=status,
                blocker=blocker,
                required_config=missing or list(contract.required_config),
                owner_action=contract.owner_action,
            )
        )

    counts = {status.value: sum(1 for item in items if item.status == status) for status in ControlTowerStatus}
    covered = counts[ControlTowerStatus.HEALTHY.value] + counts[ControlTowerStatus.WARNING.value]
    missing_seats = {
        item.seat_id
        for item in items
        if item.status in {ControlTowerStatus.AWAITING_FEED, ControlTowerStatus.UNAVAILABLE}
    }
    summary = ControlTowerSeatKpiCoverageSummary(
        total=len(items),
        healthy=counts[ControlTowerStatus.HEALTHY.value],
        warning=counts[ControlTowerStatus.WARNING.value],
        awaiting_feed=counts[ControlTowerStatus.AWAITING_FEED.value],
        unavailable=counts[ControlTowerStatus.UNAVAILABLE.value],
        coverage_pct=round((covered / len(items)) * 100, 1) if items else 0,
        seats_with_missing=len(missing_seats),
    )

    feeds = [
        ControlTowerFeedStatus(
            name="Seat KPI coverage contract",
            source_authority="K1 fixed-seat operating system + FleetPulse route registry",
            status=ControlTowerStatus.HEALTHY if summary.coverage_pct >= 80 else ControlTowerStatus.WARNING,
            message=(
                f"{covered} of {summary.total} KPI contracts have a FleetPulse route or partial route; "
                f"{summary.awaiting_feed} still need source feed/config work."
            ),
            required_config=[],
        )
    ]
    return ControlTowerSeatKpiCoverageResponse(
        generated_at=_now(),
        summary=summary,
        kpis=items,
        feeds=feeds,
    )
