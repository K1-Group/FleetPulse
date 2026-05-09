"""Fleet analytics service — overview, per-location breakdown, trip stats."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import os
from typing import Any

from geotab_client import GeotabClient
from models import FleetOverview, LocationStats, Vehicle, VehiclePosition, VehicleStatus

KM_TO_MILES = 0.621371
DEFAULT_STOP_THRESHOLD_MINUTES = 5
DEFAULT_DRIVER_LOGOUT_GAP_MINUTES = 10 * 60
DEFAULT_TARGET_TRIP_HOURS = 12

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


def get_fleet_overview() -> FleetOverview:
    client = GeotabClient.get()
    devices = client.get_devices()
    statuses = client.get_device_status_info()
    status_map = {s.get("device", {}).get("id"): s for s in statuses}

    counts = {"active": 0, "idle": 0, "parked": 0, "offline": 0}
    for dev in devices:
        sid = dev.get("id")
        st = status_map.get(sid)
        if st:
            c = _classify_status(st).value
            counts[c] = counts.get(c, 0) + 1
        else:
            counts["offline"] += 1

    now = datetime.now(timezone.utc)
    trips = client.get_trips(now - timedelta(days=1), now)
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
    )

def get_vehicles() -> list[Vehicle]:
    client = GeotabClient.get()
    devices = client.get_devices()
    statuses = client.get_device_status_info()
    status_map = {s.get("device", {}).get("id"): s for s in statuses}

    vehicles: list[Vehicle] = []
    for dev in devices:
        sid = dev.get("id")
        st = status_map.get(sid, {})
        lat = st.get("latitude", 0) or 0
        lon = st.get("longitude", 0) or 0
        vehicles.append(
            Vehicle(
                id=sid or "",
                name=dev.get("name", "Unknown"),
                status=_classify_status(st) if st else VehicleStatus.OFFLINE,
                position=VehiclePosition(
                    latitude=lat,
                    longitude=lon,
                    bearing=st.get("bearing", 0) or 0,
                    speed=st.get("speed", 0) or 0,
                )
                if lat and lon
                else None,
                location_name=_nearest_location(lat, lon) if lat and lon else None,
                last_contact=st.get("dateTime"),
            )
        )
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
