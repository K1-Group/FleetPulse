"""Read-only trailer tracking projection across Geotab GPS and XTRA events.

Geotab remains the GPS source of truth. XTRA Lease Outlook emails are event
references. Custody is inferred only from live proximity to scoped Geotab
vehicles and should be confirmed against dispatch/Xcelerator when wired.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
import os
import re
from typing import Any

from configs.xtra_lease import XtraLeaseIngestionConfig
from geotab_client import GeotabClient
from models import (
    ControlTowerFeedStatus,
    ControlTowerStatus,
    ControlTowerTrailerCustody,
    ControlTowerTrailerEvent,
    ControlTowerTrailerLiveAsset,
    ControlTowerTrailerTrackingResponse,
    ControlTowerTrailerTrackingSummary,
    VehiclePosition,
    VehicleStatus,
)
from services.fleet_service import (
    _classify_status,
    _device_group_ids,
    _is_scoped_fleet_device,
    _nearest_location,
)
from services.xtra_lease_ingestion_service import XTRA_SOURCE_AUTHORITY, get_xtra_lease_projection

TRAILER_GROUP_IDS_DEFAULT = "GroupTrailerId"
GEOTAB_SOURCE_AUTHORITY = "K1 Logistics Inc / Geotab"
CUSTODY_SOURCE = "Geotab proximity inference"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _csv_env(name: str, default: str = "") -> set[str]:
    return {item.strip() for item in os.getenv(name, default).split(",") if item.strip()}


def _feed(
    name: str,
    source_authority: str,
    status: ControlTowerStatus,
    message: str,
    required_config: list[str] | None = None,
    last_updated: datetime | None = None,
) -> ControlTowerFeedStatus:
    return ControlTowerFeedStatus(
        name=name,
        source_authority=source_authority,
        status=status,
        message=message,
        required_config=required_config or [],
        last_updated=last_updated,
    )


def _to_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _asset_key(value: str | None) -> str:
    if not value:
        return ""
    normalized = re.sub(r"[^A-Z0-9]", "", value.upper())
    for prefix in ("TRAILER", "UNIT", "XTRA"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
    return normalized


def _trailer_id_from_device(device: dict[str, Any]) -> str:
    name = str(device.get("name") or device.get("serialNumber") or device.get("id") or "Unknown")
    match = re.search(r"\b([A-Z]{1,3}\d{3,8})\b", name.upper())
    if match:
        return match.group(1)
    return name.strip()


def _status_timestamp(status: dict[str, Any]) -> datetime | None:
    return _to_utc(status.get("dateTime"))


def _is_status_stale(status: dict[str, Any], now: datetime, env_name: str, default_hours: int) -> bool:
    if not status:
        return True
    timestamp = _status_timestamp(status)
    if not timestamp:
        return True
    stale_hours = _int_env(env_name, default_hours)
    return (now - timestamp).total_seconds() > stale_hours * 3600


def _vehicle_position_from_status(
    status: dict[str, Any],
    now: datetime,
    *,
    stale_hours_env: str = "FLEETPULSE_STATUS_STALE_HOURS",
    default_stale_hours: int = 24,
) -> VehiclePosition | None:
    if _is_status_stale(status, now, stale_hours_env, default_stale_hours):
        return None
    lat = status.get("latitude") or 0
    lon = status.get("longitude") or 0
    if not lat or not lon:
        return None
    return VehiclePosition(
        latitude=float(lat),
        longitude=float(lon),
        bearing=float(status.get("bearing", 0) or 0),
        speed=float(status.get("speed", 0) or 0),
    )


def _haversine_meters(a: VehiclePosition, b: VehiclePosition) -> float:
    radius_meters = 6_371_000
    lat1 = radians(a.latitude)
    lat2 = radians(b.latitude)
    delta_lat = radians(b.latitude - a.latitude)
    delta_lon = radians(b.longitude - a.longitude)
    h = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 2 * radius_meters * asin(sqrt(h))


def _driver_value(entity: Any, *keys: str) -> str | None:
    if isinstance(entity, dict):
        for key in keys:
            value = entity.get(key)
            if value:
                return str(value)
    return None


def _latest_driver_by_device(
    client: GeotabClient,
    now: datetime,
    device_ids: set[str],
) -> dict[str, dict[str, str | None]]:
    lookback_hours = _int_env("FLEETPULSE_TRAILER_DRIVER_LOOKBACK_HOURS", 12)
    try:
        trips = client.get_trips(now - timedelta(hours=lookback_hours), now)
    except Exception:
        return {}

    latest: dict[str, tuple[datetime, dict[str, str | None]]] = {}
    for trip in trips:
        device = trip.get("device") if isinstance(trip, dict) else None
        if not isinstance(device, dict):
            continue
        device_id = str(device.get("id") or "")
        if device_id not in device_ids:
            continue
        driver = trip.get("driver")
        if not isinstance(driver, dict):
            continue
        timestamp = _to_utc(
            trip.get("stopDateTime")
            or trip.get("endDateTime")
            or trip.get("startDateTime")
            or trip.get("dateTime")
        )
        if not timestamp:
            continue
        current = latest.get(device_id)
        if current and current[0] >= timestamp:
            continue
        latest[device_id] = (
            timestamp,
            {
                "driver_id": _driver_value(driver, "id", "name"),
                "driver_name": _driver_value(driver, "name", "id"),
            },
        )
    return {device_id: driver for device_id, (_, driver) in latest.items()}


def _latest_xtra_events_by_trailer(events: list[ControlTowerTrailerEvent]) -> dict[str, ControlTowerTrailerEvent]:
    latest: dict[str, ControlTowerTrailerEvent] = {}
    for event in events:
        key = _asset_key(event.trailer_id)
        if not key:
            continue
        current = latest.get(key)
        if current is None or (event.timestamp or datetime.min.replace(tzinfo=timezone.utc)) > (
            current.timestamp or datetime.min.replace(tzinfo=timezone.utc)
        ):
            latest[key] = event
    return latest


def _vehicle_candidates(
    devices: list[dict[str, Any]],
    statuses: dict[str, dict[str, Any]],
    now: datetime,
    driver_by_device: dict[str, dict[str, str | None]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for device in devices:
        device_id = str(device.get("id") or "")
        status = statuses.get(device_id, {})
        position = _vehicle_position_from_status(status, now)
        if not device_id or position is None:
            continue
        driver = driver_by_device.get(device_id, {})
        candidates.append(
            {
                "id": device_id,
                "name": str(device.get("name") or device_id),
                "position": position,
                "driver_id": driver.get("driver_id"),
                "driver_name": driver.get("driver_name"),
            }
        )
    return candidates


def _custody_for_position(
    trailer_position: VehiclePosition | None,
    vehicles: list[dict[str, Any]],
    radius_meters: int,
) -> ControlTowerTrailerCustody:
    if trailer_position is None:
        return ControlTowerTrailerCustody(note="No current trailer GPS position from Geotab.")
    nearest: dict[str, Any] | None = None
    nearest_distance: float | None = None
    for vehicle in vehicles:
        distance = _haversine_meters(trailer_position, vehicle["position"])
        if nearest_distance is None or distance < nearest_distance:
            nearest = vehicle
            nearest_distance = distance
    if nearest is None or nearest_distance is None or nearest_distance > radius_meters:
        return ControlTowerTrailerCustody(
            confidence="none",
            source=CUSTODY_SOURCE,
            note=f"No scoped Geotab vehicle within {radius_meters} meters.",
        )
    confidence = "high" if nearest_distance <= radius_meters / 2 else "medium"
    return ControlTowerTrailerCustody(
        vehicle_id=nearest["id"],
        vehicle_name=nearest["name"],
        driver_id=nearest.get("driver_id"),
        driver_name=nearest.get("driver_name"),
        vehicle_position=nearest["position"],
        distance_meters=round(nearest_distance, 1),
        confidence=confidence,
        source=CUSTODY_SOURCE,
        note="Nearest scoped Geotab vehicle; confirm with Xcelerator dispatch assignment when available.",
    )


def get_live_trailer_tracking() -> ControlTowerTrailerTrackingResponse:
    now = _now()
    feeds: list[ControlTowerFeedStatus] = []
    trailer_assets: dict[str, ControlTowerTrailerLiveAsset] = {}
    xtra_config = XtraLeaseIngestionConfig.from_env()
    xtra_events: dict[str, ControlTowerTrailerEvent] = {}
    last_email_received: str | None = None

    try:
        xtra_projection = get_xtra_lease_projection(xtra_config)
        xtra_events = _latest_xtra_events_by_trailer(xtra_projection.events)
        last_email_received = xtra_projection.last_email_received
        feeds.append(
            _feed(
                "XTRA Outlook geofence feed",
                XTRA_SOURCE_AUTHORITY,
                ControlTowerStatus.HEALTHY if last_email_received else ControlTowerStatus.WARNING,
                "Latest XTRA geofence email events are available for trailer matching."
                if last_email_received
                else "XTRA ingestion is configured but no geofence events are available yet.",
                last_updated=_to_utc(last_email_received),
            )
        )
    except Exception as exc:
        feeds.append(
            _feed(
                "XTRA Outlook geofence feed",
                XTRA_SOURCE_AUTHORITY,
                ControlTowerStatus.UNAVAILABLE,
                f"XTRA projection unavailable: {type(exc).__name__}",
                ["FLEETPULSE_XTRA_STATE_PATH"],
            )
        )

    try:
        client = GeotabClient.get()
        devices = client.get_devices()
        statuses = client.get_device_status_info()
        status_by_device = {str(status.get("device", {}).get("id") or ""): status for status in statuses}
        trailer_group_ids = _csv_env("FLEETPULSE_TRAILER_GROUP_IDS", TRAILER_GROUP_IDS_DEFAULT)
        trailer_devices = [device for device in devices if _device_group_ids(device).intersection(trailer_group_ids)]
        vehicle_devices = [device for device in devices if _is_scoped_fleet_device(device, now)]
        vehicle_ids = {str(device.get("id") or "") for device in vehicle_devices}
        driver_by_device = _latest_driver_by_device(client, now, vehicle_ids)
        vehicles = _vehicle_candidates(vehicle_devices, status_by_device, now, driver_by_device)
        radius_meters = _int_env("FLEETPULSE_TRAILER_MATCH_RADIUS_METERS", 150)
        last_geotab_contact: datetime | None = None

        matched_xtra_keys: set[str] = set()
        for device in trailer_devices:
            geotab_device_id = str(device.get("id") or "")
            trailer_id = _trailer_id_from_device(device)
            xtra_key = _asset_key(trailer_id)
            asset_key = geotab_device_id or xtra_key or trailer_id
            status = status_by_device.get(geotab_device_id, {})
            position = _vehicle_position_from_status(
                status,
                now,
                stale_hours_env="FLEETPULSE_TRAILER_STATUS_STALE_HOURS",
                default_stale_hours=48,
            )
            timestamp = _status_timestamp(status)
            if timestamp and (last_geotab_contact is None or timestamp > last_geotab_contact):
                last_geotab_contact = timestamp
            xtra_event = xtra_events.get(xtra_key)
            if xtra_event:
                matched_xtra_keys.add(xtra_key)
            custody = _custody_for_position(position, vehicles, radius_meters)
            trailer_assets[asset_key] = ControlTowerTrailerLiveAsset(
                trailer_id=trailer_id,
                trailer_name=str(device.get("name") or trailer_id),
                geotab_device_id=geotab_device_id,
                gps_status=_classify_status(status) if position else VehicleStatus.OFFLINE,
                position=position,
                location_name=_nearest_location(position.latitude, position.longitude) if position else None,
                speed=position.speed if position else 0,
                bearing=position.bearing if position else 0,
                geotab_last_contact=timestamp,
                xtra_last_event=xtra_event,
                custody=custody,
                source_authorities=[GEOTAB_SOURCE_AUTHORITY] + ([XTRA_SOURCE_AUTHORITY] if xtra_event else []),
            )

        for key, event in xtra_events.items():
            if key in matched_xtra_keys:
                continue
            trailer_assets[key] = ControlTowerTrailerLiveAsset(
                trailer_id=event.trailer_id,
                trailer_name=event.trailer_id,
                xtra_last_event=event,
                source_authorities=[XTRA_SOURCE_AUTHORITY],
            )

        trailers = sorted(
            trailer_assets.values(),
            key=lambda trailer: (
                trailer.position is None,
                -(trailer.geotab_last_contact.timestamp() if trailer.geotab_last_contact else 0),
                trailer.trailer_id,
            ),
        )
        feeds.append(
            _feed(
                "Geotab trailer GPS feed",
                GEOTAB_SOURCE_AUTHORITY,
                ControlTowerStatus.HEALTHY,
                f"Live trailer GPS loaded from {','.join(sorted(trailer_group_ids))}.",
                last_updated=last_geotab_contact,
            )
        )
    except Exception as exc:
        trailers = list(trailer_assets.values())
        feeds.append(
            _feed(
                "Geotab trailer GPS feed",
                GEOTAB_SOURCE_AUTHORITY,
                ControlTowerStatus.UNAVAILABLE,
                f"Geotab trailer GPS unavailable: {type(exc).__name__}",
                ["FLEETPULSE_TRAILER_GROUP_IDS"],
            )
        )

    summary = ControlTowerTrailerTrackingSummary(
        total_trailers=len(trailers),
        gps_active=sum(1 for trailer in trailers if trailer.position is not None),
        gps_inactive=sum(1 for trailer in trailers if trailer.position is None),
        xtra_event_trailers=sum(1 for trailer in trailers if trailer.xtra_last_event is not None),
        custody_inferred=sum(1 for trailer in trailers if trailer.custody.vehicle_id is not None),
        custody_unassigned=sum(1 for trailer in trailers if trailer.custody.vehicle_id is None),
        last_geotab_contact=max(
            (trailer.geotab_last_contact for trailer in trailers if trailer.geotab_last_contact),
            default=None,
        ),
        last_email_received=last_email_received,
    )
    return ControlTowerTrailerTrackingResponse(
        generated_at=now,
        summary=summary,
        trailers=trailers,
        feeds=feeds,
    )
