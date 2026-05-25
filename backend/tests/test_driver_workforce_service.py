from __future__ import annotations

from datetime import datetime, timezone

from configs.driver_workforce import DriverWorkforceConfig
import services.driver_workforce_service as driver_workforce_service
from services.driver_workforce_service import (
    _build_ceo_powerbi_route_ticket_dax,
    _build_fabric_warehouse_route_ticket_sql,
    _load_route_ticket_rows,
    build_driver_workdays,
    calculate_driver_workforce_kpis,
    normalize_geotab_activity,
    normalize_route_tickets,
)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def test_cross_midnight_route_window_counts_working_driver():
    config = DriverWorkforceConfig(
        late_start_grace_minutes=15,
        near_limit_minutes=60,
        recent_driving_activity_minutes=30,
        recent_work_contact_minutes=120,
        actual_start_lookback_minutes=60,
        completion_tolerance_minutes=10,
        source_stale_minutes=180,
        timezone="America/Chicago",
    )
    tickets, invalid = normalize_route_tickets(
        [
            {
                "ticket_id": "RT-10520",
                "driver_id": "4733",
                "driver_name": "4733",
                "vehicle_name": "4733",
                "planned_start": "2026-05-20T18:00:00-05:00",
                "planned_finish": "2026-05-21T02:00:00-05:00",
                "status": "in_progress",
            }
        ],
        config=config,
    )
    assert invalid == 0

    now = _dt("2026-05-21T05:30:00Z")
    geotab = normalize_geotab_activity(
        [
            {
                "id": "b4733",
                "name": "4733",
                "status": "parked",
                "position": {"speed": 0},
                "last_contact": "2026-05-21T05:25:00Z",
            }
        ],
        [
            {
                "device": {"id": "b4733", "name": "4733"},
                "driver": {"id": "4733", "name": "4733"},
                "startDateTime": "2026-05-20T23:04:00Z",
                "stopDateTime": "2026-05-21T05:20:00Z",
            }
        ],
        now=now,
        config=config,
    )
    workdays = build_driver_workdays(tickets, geotab, now, config)

    assert workdays[0]["status"] == "working"
    assert workdays[0]["actual_worked_minutes"] == 386
    assert workdays[0]["source"] == "xcelerator_ticket_geotab_verified"
    assert calculate_driver_workforce_kpis(workdays)["working_now"] == 1


def test_late_start_does_not_count_parked_recent_contact_without_ticket_as_working():
    config = DriverWorkforceConfig(timezone="America/Chicago")
    now = _dt("2026-05-20T13:20:00Z")
    tickets, _ = normalize_route_tickets(
        [
            {
                "ticket_id": "RT-10482",
                "driver_id": "7754",
                "vehicle_name": "7754",
                "planned_start": "2026-05-20T08:00:00-05:00",
                "planned_finish": "2026-05-20T20:00:00-05:00",
                "status": "open",
            }
        ],
        config=config,
    )
    geotab = normalize_geotab_activity(
        [
            {
                "id": "b7754",
                "name": "7754",
                "status": "parked",
                "position": {"speed": 0},
                "last_contact": "2026-05-20T13:18:00Z",
            }
        ],
        [],
        now=now,
        config=config,
    )
    workdays = build_driver_workdays(tickets, geotab, now, config)

    assert workdays[0]["status"] == "late_start"
    assert calculate_driver_workforce_kpis(workdays)["working_now"] == 0


def test_active_without_ticket_requires_geotab_activity():
    config = DriverWorkforceConfig(timezone="America/Chicago")
    now = _dt("2026-05-20T18:00:00Z")
    geotab = normalize_geotab_activity(
        [
            {
                "id": "moving",
                "name": "9120",
                "status": "active",
                "position": {"speed": 43},
                "last_contact": "2026-05-20T17:55:00Z",
            },
            {
                "id": "parked",
                "name": "6418",
                "status": "parked",
                "position": {"speed": 0},
                "last_contact": "2026-05-20T17:58:00Z",
            },
        ],
        [],
        now=now,
        config=config,
    )

    workdays = build_driver_workdays([], geotab, now, config)

    assert [row["status"] for row in workdays] == ["active_without_ticket"]
    assert workdays[0]["vehicle_id"] == "moving"


def test_ceo_powerbi_route_ticket_rows_normalize_from_service_name_projection(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_DRIVER_WORKFORCE_ROUTE_SERVICE_NAMES", "Route Ticket")
    query = _build_ceo_powerbi_route_ticket_dax()

    assert "'xcelerator_review_orders'[service_name] IN { \"Route Ticket\" }" in query
    assert '"service_type", \'xcelerator_review_orders\'[service_name]' in query

    tickets, invalid = normalize_route_tickets(
        [
            {
                "[ticket_id]": "35.052126",
                "[driver_id]": "369",
                "[driver_name]": "369",
                "[route_status]": "open",
                "[pickup_location]": "Fort Worth",
                "[delivery_location]": "Fort Worth",
                "[planned_start]": "2026-05-21T11:00:00",
                "[planned_finish]": "2026-05-21T20:30:00",
                "[service_type]": "Route Ticket",
            }
        ],
        config=DriverWorkforceConfig(timezone="America/Chicago"),
    )

    assert invalid == 0
    assert tickets[0]["ticket_id"] == "35.052126"
    assert tickets[0]["driver_id"] == "369"
    assert tickets[0]["planned_start"] == _dt("2026-05-21T16:00:00Z")
    assert tickets[0]["planned_finish"] == _dt("2026-05-22T01:30:00Z")


def test_driver_workforce_source_can_target_ceo_powerbi_without_global_switch(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_DRIVER_WORKFORCE_XCELERATOR_SOURCE", "ceo_powerbi")
    monkeypatch.delenv("FLEETPULSE_XCELERATOR_SOURCE", raising=False)
    monkeypatch.setattr(
        driver_workforce_service,
        "_load_ceo_powerbi_route_ticket_rows",
        lambda: [{"ticket_id": "RT-1", "planned_start": "2026-05-21T11:00:00"}],
    )

    rows, last_updated, meta = _load_route_ticket_rows(DriverWorkforceConfig.from_env())

    assert rows[0]["ticket_id"] == "RT-1"
    assert last_updated is not None
    assert meta["xcelerator_source"] == "ceo_powerbi"
    assert meta["configured_xcelerator_source"] == "ceo_powerbi"
    assert meta["source_authority"] == "K1 Group LLC / Xcelerator CEO Dashboard Power BI semantic model"
    assert meta["ceo_powerbi_rows"] == 1


def test_driver_workforce_ceo_powerbi_can_fallback_to_fabric_warehouse(monkeypatch):
    config = DriverWorkforceConfig(
        xcelerator_source="ceo_powerbi",
        ceo_powerbi_fallback_source="fabric_warehouse_sql",
    )
    monkeypatch.setattr(
        driver_workforce_service,
        "_load_ceo_powerbi_route_ticket_rows",
        lambda: (_ for _ in ()).throw(RuntimeError("powerbi_not_authorized")),
    )
    monkeypatch.setattr(
        driver_workforce_service,
        "_load_fabric_warehouse_route_ticket_rows",
        lambda: [{"ticket_id": "RT-FABRIC"}],
    )

    rows, last_updated, meta = _load_route_ticket_rows(config)

    assert rows == [{"ticket_id": "RT-FABRIC"}]
    assert last_updated is not None
    assert meta["xcelerator_source"] == "ceo_powerbi"
    assert meta["effective_xcelerator_source"] == "fabric_warehouse_sql"
    assert meta["fabric_warehouse_rows"] == 1
    assert meta["fallback_reason"] == "RuntimeError"
    assert meta["errors"] == ["ceo_powerbi_route_tickets:RuntimeError"]


def test_fabric_warehouse_route_ticket_sql_uses_service_and_delivery_filters():
    query, params = _build_fabric_warehouse_route_ticket_sql(
        ["Route Ticket", "Linehaul"],
        "K1 Logistics Inc",
    )

    assert "FROM dbo.xcelerator_review_orders" in query
    assert "service_name IN (?, ?)" in query
    assert "delivery_center = ?" in query
    assert params == ["Route Ticket", "Linehaul", "K1 Logistics Inc"]
