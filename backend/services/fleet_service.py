"""Fleet analytics service — overview, per-location breakdown, trip stats."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
import threading
import time
from typing import Any

from geotab_client import GeotabClient
from models import FleetOverview, LocationStats, Vehicle, VehiclePosition, VehicleStatus

KM_TO_MILES = 0.621371
DEFAULT_STOP_THRESHOLD_MINUTES = 5
DEFAULT_DRIVER_LOGOUT_GAP_MINUTES = 10 * 60
DEFAULT_TARGET_TRIP_HOURS = 12
DEFAULT_DEVICE_GROUP_IDS = "GroupVehicleId"
DEFAULT_EXCLUDED_DEVICE_GROUP_IDS = "GroupTrailerId"
DEFAULT_STATUS_STALE_HOURS = 24
DEFAULT_CACHE_TTL_SECONDS = 30
DEFAULT_CACHE_FALLBACK_SECONDS = 300

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCKS: dict[str, threading.Lock] = {}

# K1 Logistics / K1 Group locations (FTW, Justin, OKC, Kansas City)
LOCATIONS = [
    {"name": "Fort Worth Yard", "address": "4200 Gravel Dr, Fort Worth, TX 76118", "lat": 32.8012, "lon": -97.2197},
    {"name": "Justin Terminal", "address": "17176 FM156, Justin, TX 76247", "lat": 33.0848, "lon": -97.2961},
    {"name": "OKC Terminal", "address": "4012 S Purdue Ave, Oklahoma City, OK 73179", "lat": 35.3922, "lon": -97.5900},
    {"name": "Kansas City Terminal", "address": "11200 N Congress Ave, Kansas City, MO 64153", "lat": 39.2967, "lon": -94.6680},
]


def _classify_status(device_status: dict[str, Any]) -> VehicleStatus:
    """Classify a vehicle as active/idle/parked based on DeviceStatusInfo."""
    speed = device_status.get("speed", 0) or 0
    is_driving = device_status.get("isDriving", False)
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
    }


def build_driver_trip_sessions(
    trips: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    stop_threshold_minutes: int | None = None,
    driver_logout_gap_minutes: int | None = None,
) -> list[dict[str, Any]]:
    """Group Geotab movement segments into K1 driver-session trips."""

    now = now or datetime.now(timezone.utc)
    stop_threshold_minutes = stop_threshold_minutes or _int_env(
        "FLEETPULSE_STOP_THRESHOLD_MINUTES", DEFAULT_STOP_THRESHOLD_MINUTES
    )
    driver_logout_gap_minutes = driver_logout_gap_minutes or _int_env(
        "FLEETPULSE_DRIVER_LOGOUT_GAP_MINUTES", DEFAULT_DRIVER_LOGOUT_GAP_MINUTES
    )

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
                current = {
                    "driver_key": driver_key,
                    "driver_name": segment.get("driver_name"),
                    "device_keys": {segment["device_key"]},
                    "device_names": {segment["device_name"]} if segment.get("device_name") else set(),
                    "start": segment["start"],
                    "end": segment["end"],
                    "distance_km": segment["distance_km"],
                    "stop_count": 0,
                    "stop_minutes": 0.0,
                    "segment_count": 1,
                }
                continue

            gap_minutes = max((segment["start"] - current["end"]).total_seconds() / 60, 0)
            if gap_minutes > driver_logout_gap_minutes:
                sessions.append(current)
                current = {
                    "driver_key": driver_key,
                    "driver_name": segment.get("driver_name"),
                    "device_keys": {segment["device_key"]},
                    "device_names": {segment["device_name"]} if segment.get("device_name") else set(),
                    "start": segment["start"],
                    "end": segment["end"],
                    "distance_km": segment["distance_km"],
                    "stop_count": 0,
                    "stop_minutes": 0.0,
                    "segment_count": 1,
                }
                continue

            if gap_minutes > stop_threshold_minutes:
                current["stop_count"] += 1
                current["stop_minutes"] += gap_minutes

            current["end"] = max(current["end"], segment["end"])
            current["distance_km"] += segment["distance_km"]
            current["segment_count"] += 1
            current["device_keys"].add(segment["device_key"])
            if segment.get("device_name"):
                current["device_names"].add(segment["device_name"])

        if current is not None:
            sessions.append(current)

    return sessions


def summarize_driver_trip_sessions(
    trips: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    stop_threshold_minutes: int | None = None,
    driver_logout_gap_minutes: int | None = None,
    target_trip_hours: float | None = None,
) -> dict[str, Any]:
    target_trip_hours = target_trip_hours or _float_env(
        "FLEETPULSE_TARGET_TRIP_HOURS", DEFAULT_TARGET_TRIP_HOURS
    )
    sessions = build_driver_trip_sessions(
        trips,
        now=now,
        stop_threshold_minutes=stop_threshold_minutes,
        driver_logout_gap_minutes=driver_logout_gap_minutes,
    )
    durations_min = [
        max((session["end"] - session["start"]).total_seconds() / 60, 0) for session in sessions
    ]
    total_distance_miles = sum(session["distance_km"] for session in sessions) * KM_TO_MILES
    trip_count = len(sessions)
    avg_duration_min = sum(durations_min) / trip_count if trip_count else 0
    avg_distance_miles = total_distance_miles / trip_count if trip_count else 0
    target_minutes = target_trip_hours * 60

    return {
        "sessions": sessions,
        "trip_count": trip_count,
        "total_stops": sum(session["stop_count"] for session in sessions),
        "total_distance_miles": round(total_distance_miles, 1),
        "avg_duration_min": round(avg_duration_min, 1),
        "avg_duration_hours": round(avg_duration_min / 60, 1),
        "avg_distance_miles": round(avg_distance_miles, 1),
        "target_trip_hours": target_trip_hours,
        "trips_meeting_target": sum(1 for minutes in durations_min if minutes >= target_minutes),
        "trips_under_target": sum(1 for minutes in durations_min if minutes < target_minutes),
    }


def _nearest_location(lat: float, lon: float) -> str | None:
    """Return nearest K1 location name if within ~500 m."""
    best, best_dist = None, 0.005  # ~500 m in degrees
    for loc in LOCATIONS:
        d = ((lat - loc["lat"]) ** 2 + (lon - loc["lon"]) ** 2) ** 0.5
        if d < best_dist:
            best, best_dist = loc["name"], d
    return best


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
    trip_metrics = summarize_driver_trip_sessions(trips, now=now)
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
        trip_definition="driver_session_with_stops_over_5_min",
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
            trip_definition="driver_session_with_stops_over_5_min",
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
            trip_definition="driver_session_with_stops_over_5_min",
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
        return fallback if fallback is not None else []

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
                vehicle_count=len(at_loc),
                active=sum(1 for v in at_loc if v.status == VehicleStatus.ACTIVE),
            )
        )
    return stats
