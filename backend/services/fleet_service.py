"""Fleet analytics service — overview, per-location breakdown, trip stats."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
import os
import threading
import time
from typing import Any

from geotab_client import GeotabClient
from models import FleetOverview, LocationStats, Vehicle, VehiclePosition, VehicleStatus
from services.hub_config_service import get_fleet_hubs

KM_TO_MILES = 0.621371
DEFAULT_STOP_THRESHOLD_MINUTES = 60
DEFAULT_DRIVER_LOGOUT_GAP_MINUTES = 10 * 60
DEFAULT_TARGET_TRIP_HOURS = 12
DEFAULT_DEVICE_GROUP_IDS = "GroupVehicleId"
DEFAULT_EXCLUDED_DEVICE_GROUP_IDS = "GroupTrailerId"
DEFAULT_STATUS_STALE_HOURS = 24
DEFAULT_CACHE_TTL_SECONDS = 30
DEFAULT_CACHE_FALLBACK_SECONDS = 300
DEFAULT_CACHE_REFRESH_WAIT_SECONDS = 30.0
EARTH_RADIUS_MILES = 3958.7613

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCKS: dict[str, threading.Lock] = {}

# K1 Logistics / K1 Group configured operating hubs.
LOCATIONS = get_fleet_hubs()


def _classify_status(device_status: dict[str, Any]) -> VehicleStatus:
    """Classify a vehicle as active/idle/parked based on DeviceStatusInfo."""
    speed = device_status.get("speed", 0) or 0
    is_driving = _bool_value(device_status.get("isDriving", False))
    if is_driving or speed > 3:
        return VehicleStatus.ACTIVE
    if speed > 0:
        return VehicleStatus.IDLE
    return VehicleStatus.PARKED


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _cache_ttl_seconds() -> int:
    return max(0, _int_env("FLEETPULSE_CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL_SECONDS))


def _cache_fallback_seconds() -> int:
    return max(_cache_ttl_seconds(), _int_env("FLEETPULSE_CACHE_FALLBACK_SECONDS", DEFAULT_CACHE_FALLBACK_SECONDS))


def _cache_refresh_wait_seconds() -> float:
    return max(0.0, _float_env("FLEETPULSE_CACHE_REFRESH_WAIT_SECONDS", DEFAULT_CACHE_REFRESH_WAIT_SECONDS))


def _cache_get(key: str, max_age_seconds: int) -> Any | None:
    if max_age_seconds <= 0:
        return None
    entry = _CACHE.get(key)
    if not entry:
        return None
    created_at, value = entry
    if time.time() - created_at > max_age_seconds:
        return None
    return deepcopy(value)


def _cache_set(key: str, value: Any) -> None:
    _CACHE[key] = (time.time(), deepcopy(value))


def _cache_wait_for_value(key: str, max_wait_seconds: float) -> Any | None:
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        cached = _cache_get(key, _cache_fallback_seconds())
        if cached is not None:
            return cached
        time.sleep(0.25)
    return None


def _acquire_cache_lock(key: str) -> threading.Lock | None:
    lock = _CACHE_LOCKS.setdefault(key, threading.Lock())
    return lock if lock.acquire(blocking=False) else None


def _with_source_mode(overview: FleetOverview, source_mode: str) -> FleetOverview:
    return overview.model_copy(update={"source_mode": source_mode})


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _csv_env(name: str, default: str) -> set[str]:
    raw = os.getenv(name, default)
    return {item.strip() for item in raw.split(",") if item.strip()}


def _to_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _path_value(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def _text_value(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, dict):
        for key in ("name", "address", "id"):
            text = _text_value(value.get(key))
            if text:
                return text
    return None


def _first_text(payload: dict[str, Any], *paths: str) -> str | None:
    for path in paths:
        text = _text_value(_path_value(payload, path))
        if text:
            return text
    return None


def _float_value(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _point_value(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    lat = next(
        (
            parsed
            for key in ("latitude", "lat", "y")
            if (parsed := _float_value(value.get(key))) is not None
        ),
        None,
    )
    lon = next(
        (
            parsed
            for key in ("longitude", "lng", "lon", "x")
            if (parsed := _float_value(value.get(key))) is not None
        ),
        None,
    )
    if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return None
    return {"latitude": lat, "longitude": lon}


def _point_from_pairs(payload: dict[str, Any], pairs: tuple[tuple[str, str], ...]) -> dict[str, float] | None:
    for lat_key, lon_key in pairs:
        lat = _float_value(_path_value(payload, lat_key))
        lon = _float_value(_path_value(payload, lon_key))
        if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
            return {"latitude": lat, "longitude": lon}
    return None


def _first_point(payload: dict[str, Any], paths: tuple[str, ...], pairs: tuple[tuple[str, str], ...]) -> dict[str, float] | None:
    for path in paths:
        point = _point_value(_path_value(payload, path))
        if point:
            return point
    return _point_from_pairs(payload, pairs)


def _first_datetime(payload: dict[str, Any], *keys: str) -> datetime | None:
    for key in keys:
        parsed = _to_utc(payload.get(key))
        if parsed:
            return parsed
    return None


def _entity_key(payload: dict[str, Any], field: str, fallback: str) -> str:
    entity = payload.get(field) or {}
    if isinstance(entity, dict):
        return str(entity.get("id") or entity.get("name") or entity.get("serialNumber") or fallback)
    return str(entity or fallback)


def _entity_name(payload: dict[str, Any], field: str) -> str | None:
    entity = payload.get(field) or {}
    if isinstance(entity, dict):
        value = entity.get("name") or entity.get("id")
        return str(value) if value else None
    return str(entity) if entity else None


def _trip_start_point(trip: dict[str, Any]) -> dict[str, float] | None:
    return _first_point(
        trip,
        (
            "startPoint",
            "start_point",
            "startLocation",
            "start_location",
            "startPosition",
            "start_position",
            "from",
            "fromPoint",
            "origin",
        ),
        (
            ("startLatitude", "startLongitude"),
            ("start_latitude", "start_longitude"),
            ("fromLatitude", "fromLongitude"),
            ("origin.latitude", "origin.longitude"),
        ),
    )


def _trip_stop_point(trip: dict[str, Any]) -> dict[str, float] | None:
    return _first_point(
        trip,
        (
            "stopPoint",
            "stop_point",
            "stopLocation",
            "stop_location",
            "stopPosition",
            "stop_position",
            "endPoint",
            "end_point",
            "endLocation",
            "end_location",
            "to",
            "toPoint",
            "destination",
        ),
        (
            ("stopLatitude", "stopLongitude"),
            ("stop_latitude", "stop_longitude"),
            ("endLatitude", "endLongitude"),
            ("destination.latitude", "destination.longitude"),
        ),
    )


def _trip_start_address(trip: dict[str, Any]) -> str | None:
    return _first_text(
        trip,
        "startAddress",
        "start_address",
        "startLocation.address",
        "start_location.address",
        "origin.address",
    )


def _trip_stop_address(trip: dict[str, Any]) -> str | None:
    return _first_text(
        trip,
        "stopAddress",
        "stop_address",
        "stopLocation.address",
        "stop_location.address",
        "endAddress",
        "end_address",
        "destination.address",
    )


def _trip_start_geofence(trip: dict[str, Any]) -> str | None:
    return _first_text(
        trip,
        "startZoneName",
        "start_zone_name",
        "startZone",
        "startZone.name",
        "startGeofenceName",
        "start_geofence_name",
        "startGeofence",
        "startGeofence.name",
    )


def _trip_stop_geofence(trip: dict[str, Any]) -> str | None:
    return _first_text(
        trip,
        "stopZoneName",
        "stop_zone_name",
        "stopZone",
        "stopZone.name",
        "stopGeofenceName",
        "stop_geofence_name",
        "stopGeofence",
        "stopGeofence.name",
        "zoneName",
        "zone.name",
        "geofenceName",
        "geofence.name",
    )


def _status_point(status: dict[str, Any]) -> dict[str, float] | None:
    return _first_point(
        status,
        (
            "location",
            "position",
            "currentLocation",
            "current_location",
            "point",
        ),
        (
            ("latitude", "longitude"),
            ("lat", "lon"),
            ("lat", "lng"),
            ("y", "x"),
        ),
    )


def _status_address(status: dict[str, Any]) -> str | None:
    return _first_text(
        status,
        "address",
        "location.address",
        "currentLocation.address",
        "current_location.address",
    )


def _status_geofence(status: dict[str, Any]) -> str | None:
    return _first_text(
        status,
        "zoneName",
        "zone.name",
        "geofenceName",
        "geofence.name",
        "geofence",
        "location.zoneName",
        "location.geofenceName",
    )


def _device_status_map(current_statuses: Any | None) -> dict[str, dict[str, Any]]:
    if not current_statuses:
        return {}
    if isinstance(current_statuses, dict):
        return {
            str(device_id): status
            for device_id, status in current_statuses.items()
            if device_id and isinstance(status, dict)
        }
    return {
        str(status.get("device", {}).get("id")): status
        for status in current_statuses
        if isinstance(status, dict) and status.get("device", {}).get("id")
    }


def _is_currently_not_moving(status: dict[str, Any]) -> bool:
    speed = _float_value(status.get("speed"))
    has_driving_signal = "isDriving" in status
    has_speed_signal = speed is not None
    if not has_driving_signal and not has_speed_signal:
        return False
    if _bool_value(status.get("isDriving", False)):
        return False
    return speed is None or speed <= 3


def _device_group_ids(device: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for group in device.get("groups") or []:
        if isinstance(group, dict):
            value = group.get("id") or group.get("name")
            if value:
                ids.add(str(value))
        elif group:
            ids.add(str(group))
    return ids


def _device_lifecycle_active(device: dict[str, Any], now: datetime) -> bool:
    active_from = _to_utc(device.get("activeFrom"))
    active_to = _to_utc(device.get("activeTo"))
    if active_from and active_from > now:
        return False
    if active_to and active_to <= now:
        return False
    return True


def _is_scoped_fleet_device(device: dict[str, Any], now: datetime) -> bool:
    """Return true for devices that should count as operational fleet vehicles."""
    if _bool_env("FLEETPULSE_REQUIRE_ACTIVE_LIFECYCLE", True) and not _device_lifecycle_active(
        device, now
    ):
        return False

    group_ids = _device_group_ids(device)
    include_groups = _csv_env("FLEETPULSE_DEVICE_GROUP_IDS", DEFAULT_DEVICE_GROUP_IDS)
    exclude_groups = _csv_env("FLEETPULSE_EXCLUDED_DEVICE_GROUP_IDS", DEFAULT_EXCLUDED_DEVICE_GROUP_IDS)
    if include_groups and not group_ids.intersection(include_groups):
        return False
    if exclude_groups and group_ids.intersection(exclude_groups):
        return False
    return True


def get_scoped_device_map(
    raw_devices: list[dict[str, Any]] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, str]:
    """Return Geotab device id -> name for the configured K1 operational fleet scope."""

    current_time = now or datetime.now(timezone.utc)
    if raw_devices is None:
        cache_key = "scoped_device_map"
        cached = _cache_get(cache_key, _cache_ttl_seconds())
        if cached is not None:
            return cached

        lock = _acquire_cache_lock(cache_key)
        if lock is None:
            fallback = _cache_get(cache_key, _cache_fallback_seconds())
            return fallback if fallback is not None else {}

        try:
            cached = _cache_get(cache_key, _cache_ttl_seconds())
            if cached is not None:
                return cached
            raw_devices = GeotabClient.get().get_devices()
            device_map = get_scoped_device_map(raw_devices, now=current_time)
            _cache_set(cache_key, device_map)
            return device_map
        finally:
            lock.release()

    return {
        str(device["id"]): str(device.get("name") or device["id"])
        for device in raw_devices
        if device.get("id") and _is_scoped_fleet_device(device, current_time)
    }


def _status_datetime(status: dict[str, Any]) -> datetime | None:
    return _to_utc(status.get("dateTime"))


def _is_status_stale(status: dict[str, Any] | None, now: datetime) -> bool:
    if not status:
        return True
    timestamp = _status_datetime(status)
    if not timestamp:
        return True
    stale_hours = _int_env("FLEETPULSE_STATUS_STALE_HOURS", DEFAULT_STATUS_STALE_HOURS)
    return (now - timestamp).total_seconds() > stale_hours * 3600


def _trip_distance_km(trip: dict[str, Any]) -> float:
    for key in ("distance", "drivingDistance", "tripDistance"):
        value = trip.get(key)
        if value is None:
            continue
        try:
            return max(float(value), 0.0)
        except (TypeError, ValueError):
            continue
    return 0.0


def _trip_segment(trip: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    start = _first_datetime(
        trip,
        "startDateTime",
        "start_date_time",
        "start",
        "startTime",
        "start_time",
        "dateTime",
    )
    stop = _first_datetime(
        trip,
        "stopDateTime",
        "stop_date_time",
        "stop",
        "stopTime",
        "stop_time",
        "endDateTime",
        "end",
    )
    if not start:
        return None
    stop = stop or now
    if stop < start:
        return None

    device_key = _entity_key(trip, "device", "unknown-device")
    driver_key = _entity_key(trip, "driver", device_key)
    return {
        "driver_key": driver_key,
        "driver_name": _entity_name(trip, "driver"),
        "device_key": device_key,
        "device_name": _entity_name(trip, "device"),
        "start": start,
        "end": stop,
        "distance_km": _trip_distance_km(trip),
        "start_point": _trip_start_point(trip),
        "end_point": _trip_stop_point(trip),
        "start_address": _trip_start_address(trip),
        "end_address": _trip_stop_address(trip),
        "start_geofence": _trip_start_geofence(trip),
        "end_geofence": _trip_stop_geofence(trip),
    }


def _new_trip_session(driver_key: str, segment: dict[str, Any]) -> dict[str, Any]:
    return {
        "driver_key": driver_key,
        "driver_name": segment.get("driver_name"),
        "device_keys": {segment["device_key"]},
        "device_names": {segment["device_name"]} if segment.get("device_name") else set(),
        "last_device_key": segment["device_key"],
        "last_device_name": segment.get("device_name"),
        "start": segment["start"],
        "end": segment["end"],
        "end_point": segment.get("end_point"),
        "end_address": segment.get("end_address"),
        "end_geofence": segment.get("end_geofence"),
        "distance_km": segment["distance_km"],
        "stop_count": 0,
        "stop_minutes": 0.0,
        "stop_events": [],
        "segment_count": 1,
    }


def _nearest_location_detail(lat: float, lon: float) -> dict[str, Any] | None:
    """Return nearest configured K1 hub if inside that hub radius."""
    best, best_dist = None, float("inf")
    for loc in LOCATIONS:
        d = _distance_miles(lat, lon, loc["lat"], loc["lon"])
        if d <= loc["radius_miles"] and d < best_dist:
            best, best_dist = loc, d
    return best


def _long_stop_event(
    current: dict[str, Any],
    next_segment: dict[str, Any],
    gap_minutes: float,
    *,
    open_stop: bool = False,
) -> dict[str, Any]:
    point = current.get("end_point") or next_segment.get("start_point")
    address = current.get("end_address") or next_segment.get("start_address")
    geofence = current.get("end_geofence") or next_segment.get("start_geofence")
    location_source = "unavailable"
    latitude = longitude = None

    if address:
        location_source = "geotab_trip_stop_address"
    elif geofence:
        location_source = "geotab_trip_stop_geofence"

    if point:
        latitude = point["latitude"]
        longitude = point["longitude"]
        hub = _nearest_location_detail(latitude, longitude)
        if hub:
            geofence = geofence or hub["name"]
            address = address or hub["address"]
            if location_source == "unavailable":
                location_source = "configured_fleet_hub_geofence"
        elif location_source == "unavailable":
            location_source = "geotab_trip_stop_point"

    location_label = address or geofence
    if not location_label and latitude is not None and longitude is not None:
        location_label = f"{latitude:.5f}, {longitude:.5f}"

    return {
        "driver_key": current["driver_key"],
        "driver_name": current.get("driver_name") or next_segment.get("driver_name"),
        "device_key": current.get("last_device_key") or next_segment["device_key"],
        "device_name": current.get("last_device_name") or next_segment.get("device_name"),
        "stopped_at": current["end"],
        "resumed_at": None if open_stop else next_segment["start"],
        "duration_minutes": round(gap_minutes, 1),
        "latitude": latitude,
        "longitude": longitude,
        "address": address,
        "geofence": geofence,
        "location_label": location_label,
        "location_source": location_source,
    }


def _append_current_not_moving_stop(
    current: dict[str, Any],
    *,
    status_by_device: dict[str, dict[str, Any]],
    now: datetime,
    stop_threshold_minutes: int,
) -> None:
    status = status_by_device.get(str(current.get("last_device_key") or ""))
    if not status or _is_status_stale(status, now) or not _is_currently_not_moving(status):
        return

    status_time = _status_datetime(status)
    if status_time and status_time < current["end"]:
        return

    gap_minutes = max((now - current["end"]).total_seconds() / 60, 0)
    if gap_minutes <= stop_threshold_minutes:
        return

    status_segment = {
        "driver_name": current.get("driver_name"),
        "device_key": current.get("last_device_key"),
        "device_name": current.get("last_device_name"),
        "start": now,
        "start_point": _status_point(status),
        "start_address": _status_address(status),
        "start_geofence": _status_geofence(status),
    }
    current["stop_count"] += 1
    current["stop_minutes"] += gap_minutes
    current["stop_events"].append(
        _long_stop_event(current, status_segment, gap_minutes, open_stop=True)
    )
    current["end"] = max(current["end"], now)


def build_driver_trip_sessions(
    trips: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    stop_threshold_minutes: int | None = None,
    driver_logout_gap_minutes: int | None = None,
    current_statuses: Any | None = None,
) -> list[dict[str, Any]]:
    """Group Geotab movement segments into K1 driver-session trips."""

    now = now or datetime.now(timezone.utc)
    stop_threshold_minutes = stop_threshold_minutes or _int_env(
        "FLEETPULSE_STOP_THRESHOLD_MINUTES", DEFAULT_STOP_THRESHOLD_MINUTES
    )
    driver_logout_gap_minutes = driver_logout_gap_minutes or _int_env(
        "FLEETPULSE_DRIVER_LOGOUT_GAP_MINUTES", DEFAULT_DRIVER_LOGOUT_GAP_MINUTES
    )
    status_by_device = _device_status_map(current_statuses)

    segments_by_driver: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trip in trips:
        segment = _trip_segment(trip, now)
        if segment:
            segments_by_driver[segment["driver_key"]].append(segment)

    sessions: list[dict[str, Any]] = []
    for driver_key, segments in segments_by_driver.items():
        current: dict[str, Any] | None = None
        for segment in sorted(segments, key=lambda item: item["start"]):
            if current is None:
                current = _new_trip_session(driver_key, segment)
                continue

            gap_minutes = max((segment["start"] - current["end"]).total_seconds() / 60, 0)
            if gap_minutes > driver_logout_gap_minutes:
                sessions.append(current)
                current = _new_trip_session(driver_key, segment)
                continue

            if gap_minutes > stop_threshold_minutes:
                current["stop_count"] += 1
                current["stop_minutes"] += gap_minutes
                current["stop_events"].append(_long_stop_event(current, segment, gap_minutes))

            current["end"] = max(current["end"], segment["end"])
            current["end_point"] = segment.get("end_point")
            current["end_address"] = segment.get("end_address")
            current["end_geofence"] = segment.get("end_geofence")
            current["distance_km"] += segment["distance_km"]
            current["segment_count"] += 1
            current["last_device_key"] = segment["device_key"]
            current["last_device_name"] = segment.get("device_name")
            current["device_keys"].add(segment["device_key"])
            if segment.get("device_name"):
                current["device_names"].add(segment["device_name"])

        if current is not None:
            _append_current_not_moving_stop(
                current,
                status_by_device=status_by_device,
                now=now,
                stop_threshold_minutes=stop_threshold_minutes,
            )
            sessions.append(current)

    return sessions


def summarize_driver_trip_sessions(
    trips: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    stop_threshold_minutes: int | None = None,
    driver_logout_gap_minutes: int | None = None,
    target_trip_hours: float | None = None,
    current_statuses: Any | None = None,
) -> dict[str, Any]:
    target_trip_hours = target_trip_hours or _float_env(
        "FLEETPULSE_TARGET_TRIP_HOURS", DEFAULT_TARGET_TRIP_HOURS
    )
    sessions = build_driver_trip_sessions(
        trips,
        now=now,
        stop_threshold_minutes=stop_threshold_minutes,
        driver_logout_gap_minutes=driver_logout_gap_minutes,
        current_statuses=current_statuses,
    )
    durations_min = [
        max((session["end"] - session["start"]).total_seconds() / 60, 0) for session in sessions
    ]
    total_distance_miles = sum(session["distance_km"] for session in sessions) * KM_TO_MILES
    trip_count = len(sessions)
    avg_duration_min = sum(durations_min) / trip_count if trip_count else 0
    avg_distance_miles = total_distance_miles / trip_count if trip_count else 0
    target_minutes = target_trip_hours * 60
    long_stops = [
        stop_event
        for session in sessions
        for stop_event in session.get("stop_events", [])
    ]

    return {
        "sessions": sessions,
        "trip_count": trip_count,
        "total_stops": sum(session["stop_count"] for session in sessions),
        "long_stops": long_stops,
        "total_distance_miles": round(total_distance_miles, 1),
        "avg_duration_min": round(avg_duration_min, 1),
        "avg_duration_hours": round(avg_duration_min / 60, 1),
        "avg_distance_miles": round(avg_distance_miles, 1),
        "target_trip_hours": target_trip_hours,
        "trips_meeting_target": sum(1 for minutes in durations_min if minutes >= target_minutes),
        "trips_under_target": sum(1 for minutes in durations_min if minutes < target_minutes),
    }


def _distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(haversine))


def _nearest_location(lat: float, lon: float) -> str | None:
    location = _nearest_location_detail(lat, lon)
    return location["name"] if location else None


def _build_fleet_overview() -> FleetOverview:
    client = GeotabClient.get()
    raw_devices = client.get_devices()
    now = datetime.now(timezone.utc)
    scoped_device_map = get_scoped_device_map(raw_devices, now=now)
    devices = [dev for dev in raw_devices if dev.get("id") in scoped_device_map]
    scoped_device_ids = set(scoped_device_map)
    statuses = client.get_device_status_info()
    status_map = {s.get("device", {}).get("id"): s for s in statuses}

    counts = {"active": 0, "idle": 0, "parked": 0, "offline": 0}
    stale_status_count = 0
    for dev in devices:
        sid = dev.get("id")
        st = status_map.get(sid)
        if st and not _is_status_stale(st, now):
            c = _classify_status(st).value
            counts[c] = counts.get(c, 0) + 1
        else:
            stale_status_count += 1
            counts["offline"] += 1

    trips = [
        trip
        for trip in client.get_trips(now - timedelta(days=1), now)
        if _entity_key(trip, "device", "") in scoped_device_ids
    ]
    stop_threshold_minutes = _int_env("FLEETPULSE_STOP_THRESHOLD_MINUTES", DEFAULT_STOP_THRESHOLD_MINUTES)
    trip_metrics = summarize_driver_trip_sessions(
        trips,
        now=now,
        stop_threshold_minutes=stop_threshold_minutes,
        current_statuses=status_map,
    )
    return FleetOverview(
        total_vehicles=len(devices),
        active=counts["active"],
        idle=counts["idle"],
        parked=counts["parked"],
        offline=counts["offline"],
        total_trips_today=trip_metrics["trip_count"],
        total_stops_today=trip_metrics["total_stops"],
        total_distance_miles=trip_metrics["total_distance_miles"],
        avg_trip_duration_min=trip_metrics["avg_duration_min"],
        avg_trip_duration_hours=trip_metrics["avg_duration_hours"],
        avg_trip_distance_miles=trip_metrics["avg_distance_miles"],
        target_trip_duration_hours=trip_metrics["target_trip_hours"],
        trips_meeting_target=trip_metrics["trips_meeting_target"],
        trips_under_target=trip_metrics["trips_under_target"],
        stop_threshold_minutes=stop_threshold_minutes,
        long_stops_today=trip_metrics["long_stops"],
        trip_definition="driver_session_with_stops_over_60_min",
        raw_device_count=len(raw_devices),
        scoped_device_count=len(devices),
        raw_status_count=len(statuses),
        stale_status_count=stale_status_count,
    )


def get_fleet_overview() -> FleetOverview:
    cached = _cache_get("fleet_overview", _cache_ttl_seconds())
    if cached is not None:
        return _with_source_mode(cached, "cached_live_filtered")

    lock = _acquire_cache_lock("fleet_overview")
    if lock is None:
        fallback = _cache_get("fleet_overview", _cache_fallback_seconds())
        if fallback is not None:
            return _with_source_mode(fallback, "cached_refresh_in_progress")
        return FleetOverview(
            source_mode="geotab_refresh_in_progress",
            trip_definition="driver_session_with_stops_over_60_min",
        )

    try:
        cached = _cache_get("fleet_overview", _cache_ttl_seconds())
        if cached is not None:
            return _with_source_mode(cached, "cached_live_filtered")
        overview = _build_fleet_overview()
    except TimeoutError:
        fallback = _cache_get("fleet_overview", _cache_fallback_seconds())
        if fallback is not None:
            return _with_source_mode(fallback, "cached_after_geotab_timeout")
        return FleetOverview(
            source_mode="geotab_unavailable",
            trip_definition="driver_session_with_stops_over_60_min",
        )
    finally:
        lock.release()

    _cache_set("fleet_overview", overview)
    return overview


def _build_vehicles() -> list[Vehicle]:
    client = GeotabClient.get()
    now = datetime.now(timezone.utc)
    devices = [dev for dev in client.get_devices() if _is_scoped_fleet_device(dev, now)]
    statuses = client.get_device_status_info()
    status_map = {s.get("device", {}).get("id"): s for s in statuses}

    vehicles: list[Vehicle] = []
    for dev in devices:
        sid = dev.get("id")
        st = status_map.get(sid, {})
        stale = _is_status_stale(st, now)
        lat = st.get("latitude", 0) or 0
        lon = st.get("longitude", 0) or 0
        vehicles.append(
            Vehicle(
                id=sid or "",
                name=dev.get("name", "Unknown"),
                status=_classify_status(st) if st and not stale else VehicleStatus.OFFLINE,
                position=VehiclePosition(
                    latitude=lat,
                    longitude=lon,
                    bearing=st.get("bearing", 0) or 0,
                    speed=st.get("speed", 0) or 0,
                )
                if lat and lon and not stale
                else None,
                location_name=_nearest_location(lat, lon) if lat and lon and not stale else None,
                last_contact=st.get("dateTime"),
            )
        )
    return vehicles


def get_vehicles() -> list[Vehicle]:
    cached = _cache_get("vehicles", _cache_ttl_seconds())
    if cached is not None:
        return cached

    lock = _acquire_cache_lock("vehicles")
    if lock is None:
        fallback = _cache_get("vehicles", _cache_fallback_seconds())
        if fallback is not None:
            return fallback
        waited = _cache_wait_for_value("vehicles", _cache_refresh_wait_seconds())
        return waited if waited is not None else []

    try:
        cached = _cache_get("vehicles", _cache_ttl_seconds())
        if cached is not None:
            return cached
        vehicles = _build_vehicles()
    except TimeoutError:
        fallback = _cache_get("vehicles", _cache_fallback_seconds())
        return fallback if fallback is not None else []
    finally:
        lock.release()

    _cache_set("vehicles", vehicles)
    return vehicles


def get_location_stats() -> list[LocationStats]:
    vehicles = get_vehicles()
    stats: list[LocationStats] = []
    for loc in LOCATIONS:
        at_loc = [v for v in vehicles if v.location_name == loc["name"]]
        stats.append(
            LocationStats(
                name=loc["name"],
                address=loc["address"],
                latitude=loc["lat"],
                longitude=loc["lon"],
                radius_miles=loc["radius_miles"],
                radius_meters=loc["radius_meters"],
                vehicle_count=len(at_loc),
                active=sum(1 for v in at_loc if v.status == VehicleStatus.ACTIVE),
            )
        )
    return stats
