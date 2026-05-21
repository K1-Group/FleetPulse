"""Driver workforce route-window projection.

Xcelerator owns planned route tickets and work windows. Geotab owns actual
activity and last-contact evidence. This service joins the two as read-only
references and never writes back to either system.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import os
import re
import threading
import time as time_module
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from configs.driver_workforce import DriverWorkforceConfig
from geotab_client import GeotabClient
from models import Alert, AlertSeverity, Vehicle
from services.fleet_service import get_scoped_device_map, get_vehicles
from services.xcelerator_event_feed_service import (
    load_xcelerator_event_state_rows,
    xcelerator_event_state_configured,
)
from services.xcelerator_review_orders_import_service import (
    XceleratorReviewOrdersStateStore,
    XceleratorReviewOrdersStateTooLarge,
)


SOURCE_AUTHORITY = "K1 Group LLC / Xcelerator route tickets + K1 Logistics Inc / Geotab activity"
PROJECTION_MODE = "read_only"
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.RLock()


STATUS_PRIORITY = {
    "overdue": 1,
    "late_start": 2,
    "active_without_ticket": 3,
    "ticket_no_activity": 4,
    "near_limit": 5,
    "working": 6,
    "scheduled": 7,
    "complete": 8,
    "unmatched": 9,
}

OPEN_STATUSES = {"open", "dispatched", "in_progress", "in progress", "active", "assigned"}
CLOSED_STATUSES = {"complete", "completed", "closed", "cancelled", "canceled"}
QUALIFYING_ACTIVITY = {
    "trip_start",
    "ignition_on",
    "driving",
    "movement",
    "stop_after_movement",
    "duty_change",
    "current_status",
}


def get_driver_workforce_dataset(
    *,
    now: datetime | None = None,
    config: DriverWorkforceConfig | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Return the current workforce projection, cached briefly for dashboards."""

    config = config or DriverWorkforceConfig.from_env()
    now = _coerce_datetime(now, config) or datetime.now(timezone.utc)
    cache_key = f"driver_workforce:{now.replace(second=0, microsecond=0).isoformat()}"
    ttl_seconds = max(_env_int("FLEETPULSE_CACHE_TTL_SECONDS", 30), 0)

    with _CACHE_LOCK:
        if not force_refresh and ttl_seconds:
            cached = _CACHE.get(cache_key)
            if cached and time_module.time() - cached[0] <= ttl_seconds:
                return deepcopy(cached[1])

    dataset = _build_driver_workforce_dataset(now=now, config=config)

    with _CACHE_LOCK:
        _CACHE[cache_key] = (time_module.time(), deepcopy(dataset))
    return dataset


def _build_driver_workforce_dataset(
    *,
    now: datetime,
    config: DriverWorkforceConfig,
) -> dict[str, Any]:
    route_rows, xcelerator_last_updated, route_source_meta = _load_route_ticket_rows()
    route_tickets, invalid_ticket_count = normalize_route_tickets(route_rows, config=config)
    operating_start, operating_end = get_operating_day_window(now, config)
    operating_tickets = [
        ticket
        for ticket in route_tickets
        if ticket["planned_start"] < operating_end and ticket["planned_finish"] > operating_start
    ]

    geotab_data = (
        _load_geotab_activity(operating_start, operating_end, now, config)
        if operating_tickets
        else {"vehicles": [], "events": [], "last_updated": None, "error": None}
    )
    workdays = build_driver_workdays(operating_tickets, geotab_data, now, config)
    kpis = calculate_driver_workforce_kpis(workdays)
    alerts = generate_driver_workforce_alerts(workdays, now, config)
    insights = generate_driver_workforce_insights(workdays, kpis, config)
    validation = _build_validation(
        workdays=workdays,
        route_row_count=len(route_rows),
        ticket_count=len(operating_tickets),
        invalid_ticket_count=invalid_ticket_count,
        xcelerator_last_updated=xcelerator_last_updated,
        geotab_last_updated=geotab_data.get("last_updated"),
        geotab_error=geotab_data.get("error"),
        config=config,
        now=now,
    )

    return {
        "generated_at": now.isoformat(),
        "projection_mode": PROJECTION_MODE,
        "source_authority": SOURCE_AUTHORITY,
        "config": config.as_dict(),
        "operating_day": {
            "start": operating_start.isoformat(),
            "end": operating_end.isoformat(),
            "timezone": config.timezone,
        },
        "source_freshness": {
            "xcelerator_tickets": xcelerator_last_updated.isoformat()
            if xcelerator_last_updated
            else None,
            "geotab": geotab_data.get("last_updated").isoformat()
            if geotab_data.get("last_updated")
            else None,
        },
        "source_meta": route_source_meta,
        "kpis": kpis,
        "workdays": [_serialize_workday(item) for item in workdays],
        "alerts": alerts,
        "insights": insights,
        "validation": validation,
    }


def normalize_route_tickets(
    rows: list[dict[str, Any]],
    *,
    config: DriverWorkforceConfig | None = None,
) -> tuple[list[dict[str, Any]], int]:
    config = config or DriverWorkforceConfig.from_env()
    tickets: list[dict[str, Any]] = []
    invalid_count = 0

    for row in rows:
        planned_start = _planned_start(row, config)
        planned_finish = _planned_finish(row, config)
        if not planned_start or not planned_finish or planned_finish <= planned_start:
            if _looks_like_route_ticket(row):
                invalid_count += 1
            continue

        ticket_id = _first_value(
            row,
            "ticket_id",
            "ticketId",
            "route_ticket",
            "routeTicket",
            "route_id",
            "routeId",
            "RouteNo",
            "Route No",
            "OrderTrackingID",
            "Order ID",
            "OrderId",
            "Load ID",
            "Shipment ID",
        )
        driver_id = _first_value(
            row,
            "driver_id",
            "driverId",
            "driver_no",
            "DriverNo",
            "Driver No",
            "driver",
            "Driver",
        )
        driver_name = _first_value(
            row,
            "driver_name",
            "driverName",
            "Driver Name",
            "DriverName",
            "driver",
            "Driver",
        )
        vehicle_id = _first_value(
            row,
            "vehicle_id",
            "vehicleId",
            "unit_id",
            "unitId",
            "truck_id",
            "Truck ID",
        )
        vehicle_name = _first_value(
            row,
            "vehicle_name",
            "vehicleName",
            "unit",
            "Unit",
            "unit_number",
            "truck",
            "Truck",
            "tractor",
            "Tractor",
        )
        completion_time = _explicit_completion_time(row, config)
        route_status = str(
            _first_value(
                row,
                "route_status",
                "routeStatus",
                "ticket_status",
                "ticketStatus",
                "status",
                "Status",
            )
            or "open"
        ).strip()

        tickets.append(
            {
                "driver_id": str(driver_id or driver_name or vehicle_name or ticket_id or "").strip(),
                "driver_name": str(driver_name or driver_id or vehicle_name or "Unassigned").strip(),
                "vehicle_id": str(vehicle_id or "").strip() or None,
                "vehicle_name": str(vehicle_name or "").strip() or None,
                "ticket_id": str(ticket_id or _stable_id("ticket", row)).strip(),
                "route_status": route_status,
                "pickup_location": str(
                    _first_value(
                        row,
                        "pickup_location",
                        "pickupLocation",
                        "origin",
                        "Origin",
                        "Pickup",
                    )
                    or ""
                ).strip()
                or None,
                "delivery_location": str(
                    _first_value(
                        row,
                        "delivery_location",
                        "deliveryLocation",
                        "destination",
                        "Destination",
                        "Delivery",
                    )
                    or ""
                ).strip()
                or None,
                "planned_start": planned_start,
                "planned_finish": planned_finish,
                "actual_start_time": _explicit_actual_start(row, config),
                "completion_time": completion_time,
                "source_updated_at": _row_timestamp(row, config),
                "raw": row,
            }
        )

    return tickets, invalid_count


def normalize_geotab_activity(
    vehicles: list[Vehicle | dict[str, Any]],
    trips: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    config: DriverWorkforceConfig | None = None,
) -> dict[str, Any]:
    config = config or DriverWorkforceConfig.from_env()
    now = _coerce_datetime(now, config) or datetime.now(timezone.utc)
    normalized_vehicles = []
    events = []
    last_updated: datetime | None = None

    for vehicle in vehicles:
        data = vehicle.model_dump() if hasattr(vehicle, "model_dump") else dict(vehicle)
        last_contact = _coerce_datetime(data.get("last_contact"), config)
        position = data.get("position") or {}
        speed = _number(position.get("speed")) if isinstance(position, dict) else 0
        status = str(data.get("status") or "").lower()
        item = {
            "vehicle_id": str(data.get("id") or ""),
            "vehicle_name": str(data.get("name") or data.get("id") or ""),
            "status": status,
            "speed": speed,
            "last_contact": last_contact,
            "location_name": data.get("location_name"),
        }
        normalized_vehicles.append(item)
        if last_contact:
            last_updated = max(last_updated, last_contact) if last_updated else last_contact
            if status in {"active", "idle"} or speed > 0:
                events.append(
                    {
                        "event_type": "current_status",
                        "driver_id": None,
                        "driver_name": None,
                        "vehicle_id": item["vehicle_id"],
                        "vehicle_name": item["vehicle_name"],
                        "timestamp": last_contact,
                        "speed": speed,
                    }
                )

    for trip in trips:
        start = _trip_datetime(trip, config, start=True)
        end = _trip_datetime(trip, config, start=False) or now
        vehicle_id = _entity_id(trip.get("device")) or _first_value(trip, "vehicle_id", "vehicleId")
        vehicle_name = _entity_name(trip.get("device")) or _first_value(trip, "vehicle_name", "vehicleName")
        driver_id = _entity_id(trip.get("driver")) or _first_value(trip, "driver_id", "driverId")
        driver_name = _entity_name(trip.get("driver")) or _first_value(trip, "driver_name", "driverName")
        if start:
            events.append(
                {
                    "event_type": "trip_start",
                    "driver_id": str(driver_id or ""),
                    "driver_name": str(driver_name or ""),
                    "vehicle_id": str(vehicle_id or ""),
                    "vehicle_name": str(vehicle_name or ""),
                    "timestamp": start,
                }
            )
            last_updated = max(last_updated, start) if last_updated else start
        if end:
            events.append(
                {
                    "event_type": "stop_after_movement",
                    "driver_id": str(driver_id or ""),
                    "driver_name": str(driver_name or ""),
                    "vehicle_id": str(vehicle_id or ""),
                    "vehicle_name": str(vehicle_name or ""),
                    "timestamp": end,
                }
            )
            last_updated = max(last_updated, end) if last_updated else end

    return {
        "vehicles": normalized_vehicles,
        "events": sorted(events, key=lambda item: item["timestamp"]),
        "last_updated": last_updated,
        "error": None,
    }


def build_driver_workdays(
    route_tickets: list[dict[str, Any]],
    geotab_data: dict[str, Any],
    now: datetime,
    config: DriverWorkforceConfig,
) -> list[dict[str, Any]]:
    workdays: list[dict[str, Any]] = []
    matched_vehicle_ids: set[str] = set()

    for ticket in route_tickets:
        match = _match_ticket_to_geotab(ticket, geotab_data)
        if match and match.get("vehicle_id"):
            matched_vehicle_ids.add(str(match["vehicle_id"]))

        actual_start = ticket.get("actual_start_time") or find_actual_start(
            ticket,
            match.get("events", []) if match else [],
            config,
        )
        actual_last_seen = _find_last_activity(match)
        completion_time = ticket.get("completion_time")
        planned_start = ticket["planned_start"]
        planned_finish = ticket["planned_finish"]
        worked_minutes = None
        if actual_start:
            finish_for_worked = completion_time or now
            worked_minutes = max(_diff_minutes(finish_for_worked, actual_start), 0)
        remaining_minutes = _diff_minutes(planned_finish, now)
        workday = {
            "driver_id": ticket.get("driver_id"),
            "driver_name": ticket.get("driver_name"),
            "vehicle_id": (match or {}).get("vehicle_id") or ticket.get("vehicle_id"),
            "vehicle_name": (match or {}).get("vehicle_name") or ticket.get("vehicle_name"),
            "ticket_id": ticket.get("ticket_id"),
            "route_status": ticket.get("route_status") or "open",
            "pickup_location": ticket.get("pickup_location"),
            "delivery_location": ticket.get("delivery_location"),
            "planned_start": planned_start,
            "planned_finish": planned_finish,
            "planned_hours": round(_diff_minutes(planned_finish, planned_start) / 60, 1),
            "actual_start_time": actual_start,
            "actual_last_seen": actual_last_seen,
            "actual_worked_minutes": worked_minutes,
            "remaining_minutes": remaining_minutes,
            "variance_minutes": _diff_minutes(actual_start, planned_start) if actual_start else None,
            "completion_time": completion_time,
            "source": _source_confidence(ticket, match),
            "match_confidence": (match or {}).get("confidence") or "unmatched",
            "overlap_issue": False,
        }
        workday["status"] = get_driver_workday_status(workday, now, config)
        workdays.append(workday)

    for active in _active_without_ticket_workdays(geotab_data, matched_vehicle_ids, now, config):
        workdays.append(active)

    _mark_overlapping_tickets(workdays)
    return sort_driver_workdays(workdays)


def find_actual_start(
    ticket: dict[str, Any],
    geotab_events: list[dict[str, Any]],
    config: DriverWorkforceConfig,
) -> datetime | None:
    earliest = ticket["planned_start"] - timedelta(minutes=config.actual_start_lookback_minutes)
    latest = ticket.get("completion_time") or datetime.now(timezone.utc) + timedelta(days=1)
    candidates = [
        event["timestamp"]
        for event in geotab_events
        if event.get("timestamp")
        and earliest <= event["timestamp"] <= latest
        and str(event.get("event_type") or "") in QUALIFYING_ACTIVITY
    ]
    return min(candidates) if candidates else None


def get_driver_workday_status(
    workday: dict[str, Any],
    now: datetime,
    config: DriverWorkforceConfig,
) -> str:
    if workday.get("status") == "active_without_ticket":
        return "active_without_ticket"

    planned_start = workday["planned_start"]
    planned_finish = workday["planned_finish"]
    route_status = str(workday.get("route_status") or "").strip().lower()
    is_closed = route_status in CLOSED_STATUSES
    actual_start = workday.get("actual_start_time")
    last_seen = workday.get("actual_last_seen")

    if is_closed:
        return "complete"
    if now > planned_finish:
        return "overdue"
    if not actual_start and now > planned_start + timedelta(minutes=config.late_start_grace_minutes):
        return "late_start"
    if actual_start and last_seen:
        contact_age = _diff_minutes(now, last_seen)
        if contact_age > config.recent_work_contact_minutes:
            return "ticket_no_activity"
    if actual_start and now >= planned_finish - timedelta(minutes=config.near_limit_minutes):
        return "near_limit"
    if actual_start:
        return "working"
    if now < planned_start:
        return "scheduled"
    if workday.get("source") == "ticket_no_geotab_activity":
        return "ticket_no_activity"
    return "unmatched"


def calculate_driver_workforce_kpis(workdays: list[dict[str, Any]]) -> dict[str, Any]:
    scheduled_driver_ids = {
        str(workday.get("driver_id") or workday.get("driver_name") or workday.get("ticket_id"))
        for workday in workdays
        if workday.get("ticket_id")
    }
    working = [
        item
        for item in workdays
        if item.get("status") in {"working", "near_limit", "overdue"}
        and item.get("actual_worked_minutes") is not None
    ]
    active_worked = [int(item["actual_worked_minutes"]) for item in working]
    avg_worked = round(sum(active_worked) / len(active_worked)) if active_worked else None
    return {
        "scheduled_today": len(scheduled_driver_ids),
        "working_now": len(
            {
                str(item.get("driver_id") or item.get("driver_name") or item.get("ticket_id"))
                for item in workdays
                if item.get("status") in {"working", "near_limit", "overdue"}
            }
        ),
        "late_start": sum(1 for item in workdays if item.get("status") == "late_start"),
        "near_limit": sum(1 for item in workdays if item.get("status") == "near_limit"),
        "overdue": sum(1 for item in workdays if item.get("status") == "overdue"),
        "avg_time_worked_minutes": avg_worked,
        "active_without_ticket": sum(
            1 for item in workdays if item.get("status") == "active_without_ticket"
        ),
        "ticket_no_activity": sum(
            1 for item in workdays if item.get("status") == "ticket_no_activity"
        ),
    }


def generate_driver_workforce_alerts(
    workdays: list[dict[str, Any]],
    now: datetime,
    config: DriverWorkforceConfig,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for item in workdays:
        status = item.get("status")
        ticket_id = item.get("ticket_id") or "unmatched"
        driver_name = item.get("driver_name") or item.get("vehicle_name") or "Unknown"
        vehicle_id = str(item.get("vehicle_id") or item.get("driver_id") or ticket_id)
        vehicle_name = str(item.get("vehicle_name") or driver_name)
        message = ""
        severity = "medium"
        alert_type = status
        if status == "late_start":
            late = max(_diff_minutes(now, item["planned_start"]), 0)
            message = f"Driver {driver_name} is {late} minutes past scheduled start for ticket {ticket_id}."
        elif status == "near_limit":
            remaining = max(int(item.get("remaining_minutes") or 0), 0)
            message = f"Driver {driver_name} has {remaining} minutes remaining on route ticket {ticket_id}."
        elif status == "overdue":
            overdue = max(_diff_minutes(now, item["planned_finish"]), 0)
            message = f"Driver {driver_name} is overdue on ticket {ticket_id} by {overdue} minutes."
            severity = "critical"
        elif status == "active_without_ticket":
            message = f"Vehicle/driver {vehicle_name} is active but no open Xcelerator route ticket was matched."
        elif status == "ticket_no_activity":
            message = f"Ticket {ticket_id} is scheduled but no Geotab activity has been detected."
        elif status == "complete" and item.get("completion_time") and item.get("planned_finish"):
            late = _diff_minutes(item["completion_time"], item["planned_finish"])
            if late > config.completion_tolerance_minutes:
                alert_type = "completed_late"
                severity = "low" if late <= config.near_limit_minutes else "medium"
                message = f"Driver {driver_name} completed ticket {ticket_id} {late} minutes late."

        if not message:
            continue
        alerts.append(
            {
                "id": _stable_id("driver-workforce-alert", ticket_id, status, vehicle_id),
                "vehicle_id": vehicle_id,
                "vehicle_name": vehicle_name,
                "alert_type": alert_type,
                "severity": severity,
                "message": message,
                "timestamp": now.isoformat(),
                "acknowledged": False,
                "category": "Driver Workforce",
            }
        )
    return alerts


def generate_driver_workforce_insights(
    workdays: list[dict[str, Any]],
    kpis: dict[str, Any],
    config: DriverWorkforceConfig,
) -> list[str]:
    insights: list[str] = []
    if kpis.get("near_limit"):
        insights.append(
            f"{kpis['near_limit']} drivers are within {config.near_limit_minutes} minutes of planned route finish."
        )
    if kpis.get("overdue"):
        insights.append(f"{kpis['overdue']} route tickets are overdue and still open.")
    if kpis.get("active_without_ticket"):
        insights.append(
            f"{kpis['active_without_ticket']} active vehicle has no matching Xcelerator ticket."
        )
    if kpis.get("late_start"):
        insights.append(
            f"{kpis['late_start']} scheduled drivers have not started within the grace window."
        )
    long_running = [
        item
        for item in workdays
        if item.get("actual_worked_minutes") is not None
        and item.get("status") in {"working", "near_limit", "overdue"}
    ]
    if long_running:
        driver = max(long_running, key=lambda item: item.get("actual_worked_minutes") or 0)
        insights.append(
            f"Driver {driver.get('driver_name')} has worked {format_duration(driver.get('actual_worked_minutes'))} against a {driver.get('planned_hours')}h planned route window."
        )
    return insights


def format_duration(minutes: int | float | None) -> str:
    if minutes is None:
        return "--"
    rounded = int(round(float(minutes)))
    negative = rounded < 0
    rounded = abs(rounded)
    hours, mins = divmod(rounded, 60)
    value = f"{hours}h {mins:02d}m" if hours else f"{mins}m"
    return f"Overdue {value}" if negative else value


def format_route_window(start: datetime | None, finish: datetime | None) -> str:
    if not start or not finish:
        return "--"
    return f"{start.strftime('%-I:%M %p')} - {finish.strftime('%-I:%M %p')}"


def sort_driver_workdays(workdays: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(item: dict[str, Any]) -> tuple[int, datetime, int]:
        status = str(item.get("status") or "unmatched")
        primary_date = item.get("planned_finish") if status in {"working", "near_limit", "overdue"} else item.get("planned_start")
        worked = int(item.get("actual_worked_minutes") or 0)
        return (STATUS_PRIORITY.get(status, 99), primary_date or datetime.max.replace(tzinfo=timezone.utc), -worked)

    return sorted(workdays, key=key)


def get_operating_day_window(
    now: datetime,
    config: DriverWorkforceConfig | None = None,
) -> tuple[datetime, datetime]:
    config = config or DriverWorkforceConfig.from_env()
    tz = _timezone(config)
    local_now = now.astimezone(tz)
    start = datetime.combine(local_now.date(), time.min, tz)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def driver_workforce_alert_models(now: datetime | None = None) -> list[Alert]:
    dataset = get_driver_workforce_dataset(now=now)
    alerts: list[Alert] = []
    for item in dataset.get("alerts", []):
        severity_text = str(item.get("severity") or "medium").lower()
        severity = AlertSeverity(severity_text) if severity_text in AlertSeverity._value2member_map_ else AlertSeverity.MEDIUM
        alerts.append(
            Alert(
                id=str(item.get("id") or _stable_id("driver-workforce", item)),
                vehicle_id=str(item.get("vehicle_id") or ""),
                vehicle_name=str(item.get("vehicle_name") or "Driver Workforce"),
                alert_type=str(item.get("alert_type") or "driver_workforce"),
                severity=severity,
                message=str(item.get("message") or ""),
                timestamp=_coerce_datetime(item.get("timestamp"), DriverWorkforceConfig.from_env())
                or datetime.now(timezone.utc),
                acknowledged=bool(item.get("acknowledged")),
            )
        )
    return alerts


def _load_route_ticket_rows() -> tuple[list[dict[str, Any]], datetime | None, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    meta: dict[str, Any] = {
        "xcelerator_event_state_configured": xcelerator_event_state_configured(),
        "xcelerator_event_rows": 0,
        "review_orders_rows": 0,
        "errors": [],
    }
    last_updated: datetime | None = None
    try:
        event_rows, event_last_updated = load_xcelerator_event_state_rows()
        rows.extend(event_rows)
        meta["xcelerator_event_rows"] = len(event_rows)
        last_updated = event_last_updated
    except Exception as exc:
        meta["errors"].append(f"xcelerator_event_state:{type(exc).__name__}")

    include_review_orders = os.getenv(
        "FLEETPULSE_DRIVER_WORKFORCE_INCLUDE_REVIEW_ORDERS", ""
    ).strip().lower() in {"1", "true", "yes", "on"}
    if include_review_orders:
        try:
            review_store = XceleratorReviewOrdersStateStore()
            review_rows = review_store.rows()
            rows.extend(review_rows)
            meta["review_orders_rows"] = len(review_rows)
            if review_store.path.exists():
                file_updated = datetime.fromtimestamp(review_store.path.stat().st_mtime, timezone.utc)
                last_updated = max(last_updated, file_updated) if last_updated else file_updated
        except XceleratorReviewOrdersStateTooLarge as exc:
            meta["errors"].append(f"xcelerator_review_orders_state_too_large:{exc.size}")
        except Exception as exc:
            meta["errors"].append(f"xcelerator_review_orders:{type(exc).__name__}")
    return rows, last_updated, meta


def _load_geotab_activity(
    operating_start: datetime,
    operating_end: datetime,
    now: datetime,
    config: DriverWorkforceConfig,
) -> dict[str, Any]:
    start = operating_start - timedelta(minutes=config.actual_start_lookback_minutes)
    end = max(now, operating_end)
    try:
        vehicles = get_vehicles()
        client = GeotabClient.get()
        scoped_devices = set(get_scoped_device_map().keys())
        trips = [
            trip
            for trip in client.get_trips(start, end)
            if not scoped_devices or (_entity_id(trip.get("device")) in scoped_devices)
        ]
        return normalize_geotab_activity(vehicles, trips, now=now, config=config)
    except Exception as exc:
        return {
            "vehicles": [],
            "events": [],
            "last_updated": None,
            "error": type(exc).__name__,
        }


def _match_ticket_to_geotab(ticket: dict[str, Any], geotab_data: dict[str, Any]) -> dict[str, Any] | None:
    driver_id = _identity(ticket.get("driver_id"))
    driver_name = _identity(ticket.get("driver_name"))
    vehicle_id = _identity(ticket.get("vehicle_id"))
    vehicle_name = _identity(ticket.get("vehicle_name"))
    events = geotab_data.get("events", [])
    vehicles = geotab_data.get("vehicles", [])

    def event_matches(event: dict[str, Any]) -> bool:
        return any(
            (
                driver_id and _identity(event.get("driver_id")) == driver_id,
                driver_name and _identity(event.get("driver_name")) == driver_name,
                vehicle_id and _identity(event.get("vehicle_id")) == vehicle_id,
                vehicle_name and _identity(event.get("vehicle_name")) == vehicle_name,
            )
        )

    matched_events = [event for event in events if event_matches(event)]
    matched_vehicle = None
    for vehicle in vehicles:
        if (
            vehicle_id
            and _identity(vehicle.get("vehicle_id")) == vehicle_id
            or vehicle_name
            and _identity(vehicle.get("vehicle_name")) == vehicle_name
        ):
            matched_vehicle = vehicle
            break

    if not matched_events and not matched_vehicle:
        return None

    vehicle_id_value = (
        (matched_vehicle or {}).get("vehicle_id")
        or next((event.get("vehicle_id") for event in matched_events if event.get("vehicle_id")), None)
        or ticket.get("vehicle_id")
    )
    vehicle_name_value = (
        (matched_vehicle or {}).get("vehicle_name")
        or next((event.get("vehicle_name") for event in matched_events if event.get("vehicle_name")), None)
        or ticket.get("vehicle_name")
    )
    confidence = (
        "driver_id"
        if driver_id and any(_identity(event.get("driver_id")) == driver_id for event in matched_events)
        else "vehicle_id"
        if vehicle_id and vehicle_id_value
        else "vehicle_name"
    )
    if matched_vehicle and matched_vehicle.get("last_contact"):
        matched_events.append(
            {
                "event_type": "last_contact",
                "vehicle_id": vehicle_id_value,
                "vehicle_name": vehicle_name_value,
                "timestamp": matched_vehicle["last_contact"],
            }
        )
    return {
        "vehicle_id": vehicle_id_value,
        "vehicle_name": vehicle_name_value,
        "events": sorted(
            [event for event in matched_events if event.get("timestamp")],
            key=lambda item: item["timestamp"],
        ),
        "confidence": confidence,
    }


def _active_without_ticket_workdays(
    geotab_data: dict[str, Any],
    matched_vehicle_ids: set[str],
    now: datetime,
    config: DriverWorkforceConfig,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    recent_cutoff = now - timedelta(minutes=config.recent_driving_activity_minutes)
    for vehicle in geotab_data.get("vehicles", []):
        vehicle_id = str(vehicle.get("vehicle_id") or "")
        if not vehicle_id or vehicle_id in matched_vehicle_ids:
            continue
        last_contact = vehicle.get("last_contact")
        if not last_contact or last_contact < recent_cutoff:
            continue
        if str(vehicle.get("status") or "").lower() not in {"active", "idle"} and not (vehicle.get("speed") or 0) > 0:
            continue
        rows.append(
            {
                "driver_id": vehicle_id,
                "driver_name": vehicle.get("vehicle_name") or vehicle_id,
                "vehicle_id": vehicle_id,
                "vehicle_name": vehicle.get("vehicle_name") or vehicle_id,
                "ticket_id": None,
                "route_status": "unmatched",
                "pickup_location": vehicle.get("location_name"),
                "delivery_location": None,
                "planned_start": last_contact,
                "planned_finish": last_contact,
                "planned_hours": 0,
                "actual_start_time": last_contact,
                "actual_last_seen": last_contact,
                "actual_worked_minutes": None,
                "remaining_minutes": None,
                "variance_minutes": None,
                "completion_time": None,
                "source": "geotab_activity_no_ticket",
                "status": "active_without_ticket",
                "match_confidence": "geotab_activity_no_ticket",
                "overlap_issue": False,
            }
        )
    return rows


def _mark_overlapping_tickets(workdays: list[dict[str, Any]]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in workdays:
        if not item.get("ticket_id"):
            continue
        driver = str(item.get("driver_id") or item.get("driver_name") or "")
        grouped.setdefault(driver, []).append(item)
    for rows in grouped.values():
        sorted_rows = sorted(rows, key=lambda item: item["planned_start"])
        for index, item in enumerate(sorted_rows[1:], start=1):
            previous = sorted_rows[index - 1]
            if previous["planned_finish"] > item["planned_start"]:
                previous["overlap_issue"] = True
                item["overlap_issue"] = True


def _source_confidence(ticket: dict[str, Any], match: dict[str, Any] | None) -> str:
    if match and match.get("confidence") in {"driver_id", "driver_name"}:
        return "xcelerator_ticket_geotab_verified"
    if match:
        return "xcelerator_ticket_vehicle_derived"
    return "ticket_no_geotab_activity"


def _find_last_activity(match: dict[str, Any] | None) -> datetime | None:
    if not match:
        return None
    timestamps = [event.get("timestamp") for event in match.get("events", []) if event.get("timestamp")]
    return max(timestamps) if timestamps else None


def _build_validation(
    *,
    workdays: list[dict[str, Any]],
    route_row_count: int,
    ticket_count: int,
    invalid_ticket_count: int,
    xcelerator_last_updated: datetime | None,
    geotab_last_updated: datetime | None,
    geotab_error: str | None,
    config: DriverWorkforceConfig,
    now: datetime,
) -> dict[str, Any]:
    stale_cutoff = now - timedelta(minutes=config.source_stale_minutes)
    joined = sum(1 for item in workdays if str(item.get("source") or "").startswith("xcelerator_ticket_geotab"))
    if ticket_count == 0:
        return {
            "state": "no_data" if route_row_count == 0 else "pending",
            "status": "pending_no_data",
            "message": (
                "No route tickets found for the current operating day."
                if route_row_count
                else "No Xcelerator route-ticket rows are available for this operating day."
            ),
            "row_count": 0,
            "joined_count": 0,
            "invalid_ticket_count": invalid_ticket_count,
        }
    if geotab_error:
        return {
            "state": "failed",
            "status": "failed",
            "message": f"Failed loading Geotab activity while joining route tickets: {geotab_error}.",
            "row_count": ticket_count,
            "joined_count": joined,
            "invalid_ticket_count": invalid_ticket_count,
        }
    if xcelerator_last_updated and xcelerator_last_updated < stale_cutoff:
        return {
            "state": "stale",
            "status": "stale",
            "message": "Xcelerator route ticket data is older than the allowed freshness threshold.",
            "row_count": ticket_count,
            "joined_count": joined,
            "invalid_ticket_count": invalid_ticket_count,
        }
    if geotab_last_updated and geotab_last_updated < stale_cutoff:
        return {
            "state": "stale",
            "status": "stale",
            "message": "Geotab activity data is older than the allowed freshness threshold.",
            "row_count": ticket_count,
            "joined_count": joined,
            "invalid_ticket_count": invalid_ticket_count,
        }
    if joined:
        return {
            "state": "verified",
            "status": "verified",
            "message": "Verified: planned route windows from Xcelerator; actual activity from Geotab.",
            "row_count": ticket_count,
            "joined_count": joined,
            "invalid_ticket_count": invalid_ticket_count,
        }
    return {
        "state": "pending",
        "status": "pending",
        "message": "Partial: route tickets loaded; Geotab activity missing for some drivers.",
        "row_count": ticket_count,
        "joined_count": joined,
        "invalid_ticket_count": invalid_ticket_count,
    }


def _serialize_workday(item: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(item)
    serialized.pop("raw", None)
    for key in (
        "planned_start",
        "planned_finish",
        "actual_start_time",
        "actual_last_seen",
        "completion_time",
    ):
        if isinstance(serialized.get(key), datetime):
            serialized[key] = serialized[key].isoformat()
    serialized["status_label"] = _status_label(str(item.get("status") or "unmatched"))
    serialized["time_worked_display"] = format_duration(item.get("actual_worked_minutes"))
    serialized["remaining_display"] = format_duration(item.get("remaining_minutes"))
    return serialized


def _status_label(status: str) -> str:
    return {
        "active_without_ticket": "Active Without Ticket",
        "ticket_no_activity": "Ticket No Activity",
        "late_start": "Late Start",
        "near_limit": "Near Limit",
    }.get(status, status.replace("_", " ").title())


def _planned_start(row: dict[str, Any], config: DriverWorkforceConfig) -> datetime | None:
    return _first_datetime_value(
        row,
        config,
        "planned_start",
        "plannedStart",
        "pickup_time",
        "pickupTime",
        "pickup_start",
        "pickupStart",
        "pickup_datetime",
        "pickupDateTime",
        "start_time",
        "startTime",
        "scheduled_start",
        "scheduledStart",
    ) or _combine_date_time(
        row,
        config,
        ("[P]From Date", "PFrom Date", "From Date", "Pickup Date", "Start Date", "date", "Date"),
        ("Pickup Time", "Pickup Start Time", "Start Time", "pickup_time"),
    )


def _planned_finish(row: dict[str, Any], config: DriverWorkforceConfig) -> datetime | None:
    return _first_datetime_value(
        row,
        config,
        "planned_finish",
        "plannedFinish",
        "delivery_time",
        "deliveryTime",
        "delivery_finish",
        "deliveryFinish",
        "delivery_datetime",
        "deliveryDateTime",
        "finish_time",
        "finishTime",
        "scheduled_finish",
        "scheduledFinish",
        "deliver_by",
        "deliverBy",
    ) or _combine_date_time(
        row,
        config,
        ("[P]To Date", "PTo Date", "To Date", "Delivery Date", "Finish Date", "date", "Date"),
        ("Delivery Time", "Deliver Time", "Finish Time", "delivery_time"),
    )


def _explicit_actual_start(row: dict[str, Any], config: DriverWorkforceConfig) -> datetime | None:
    return _first_datetime_value(
        row,
        config,
        "actual_start_time",
        "actualStartTime",
        "actual_start",
        "actualStart",
    )


def _explicit_completion_time(row: dict[str, Any], config: DriverWorkforceConfig) -> datetime | None:
    return _first_datetime_value(
        row,
        config,
        "completion_time",
        "completionTime",
        "closed_at",
        "closedAt",
        "route_closed_at",
        "routeClosedAt",
    )


def _looks_like_route_ticket(row: dict[str, Any]) -> bool:
    keys = {_normalize_key(key) for key in row}
    route_keys = {
        "ticketid",
        "routeticket",
        "routeid",
        "routeno",
        "plannedstart",
        "plannedfinish",
        "pickuptime",
        "deliverytime",
    }
    return bool(keys.intersection(route_keys))


def _first_datetime_value(row: dict[str, Any], config: DriverWorkforceConfig, *aliases: str) -> datetime | None:
    value = _first_value(row, *aliases)
    return _coerce_datetime(value, config)


def _combine_date_time(
    row: dict[str, Any],
    config: DriverWorkforceConfig,
    date_aliases: tuple[str, ...],
    time_aliases: tuple[str, ...],
) -> datetime | None:
    raw_date = _first_value(row, *date_aliases)
    raw_time = _first_value(row, *time_aliases)
    parsed = _coerce_datetime(raw_date, config)
    if parsed and _value_contains_time(raw_date):
        return parsed
    day = _coerce_date(raw_date)
    if not day or raw_time in (None, ""):
        return parsed
    clock = _coerce_time(raw_time)
    if not clock:
        return parsed
    tz = _timezone(config)
    return datetime.combine(day, clock, tz).astimezone(timezone.utc)


def _row_timestamp(row: dict[str, Any], config: DriverWorkforceConfig) -> datetime | None:
    return _first_datetime_value(
        row,
        config,
        "timestamp",
        "updated_at",
        "updatedAt",
        "created_at",
        "createdAt",
        "detected_at",
        "detectedAt",
    )


def _trip_datetime(trip: dict[str, Any], config: DriverWorkforceConfig, *, start: bool) -> datetime | None:
    aliases = (
        ("startDateTime", "start_date_time", "start", "startTime", "start_time", "dateTime")
        if start
        else ("stopDateTime", "stop_date_time", "stop", "stopTime", "stop_time", "endDateTime", "end")
    )
    return _first_datetime_value(trip, config, *aliases)


def _first_value(row: dict[str, Any], *aliases: str) -> Any:
    normalized = {_normalize_key(alias) for alias in aliases}
    for key, value in row.items():
        if _normalize_key(key) in normalized and value not in (None, ""):
            return value
    return None


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _coerce_datetime(value: Any, config: DriverWorkforceConfig) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=_timezone(config)).astimezone(timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, _timezone(config)).astimezone(timezone.utc)
    if isinstance(value, (int, float)) and value > 20000:
        return datetime(1899, 12, 30, tzinfo=_timezone(config)) + timedelta(days=float(value))
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in (
            "%m/%d/%Y %I:%M %p",
            "%m/%d/%y %I:%M %p",
            "%m/%d/%Y %H:%M",
            "%m/%d/%y %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%m/%d/%Y",
            "%m/%d/%y",
            "%Y-%m-%d",
        ):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                parsed = None  # type: ignore[assignment]
        if parsed is None:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_timezone(config))
    return parsed.astimezone(timezone.utc)


def _coerce_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and value > 20000:
        return (date(1899, 12, 30) + timedelta(days=int(value)))
    text = str(value or "").strip()
    if not text:
        return None
    token = text.split()[0]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(token.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _coerce_time(value: Any) -> time | None:
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, (int, float)) and 0 <= float(value) < 1:
        seconds = int(round(float(value) * 24 * 60 * 60))
        return (datetime.combine(date.today(), time.min) + timedelta(seconds=seconds)).time()
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%I:%M %p", "%I:%M:%S %p", "%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text.upper(), fmt).time()
        except ValueError:
            continue
    return None


def _value_contains_time(value: Any) -> bool:
    return isinstance(value, datetime) or bool(re.search(r"\d{1,2}:\d{2}", str(value or "")))


def _timezone(config: DriverWorkforceConfig) -> ZoneInfo:
    try:
        return ZoneInfo(config.timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("America/Chicago")


def _entity_id(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("id") or value.get("name") or value.get("serialNumber") or "")
    return str(value or "")


def _entity_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("id") or "")
    return str(value or "")


def _identity(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _diff_minutes(end: datetime | None, start: datetime | None) -> int:
    if not end or not start:
        return 0
    return int(round((end - start).total_seconds() / 60))


def _stable_id(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:16]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
