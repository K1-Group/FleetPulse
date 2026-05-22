"""Data Connector endpoints – pre-aggregated fleet KPIs via Geotab OData.

Discovery rules:
  1. Honors a GEOTAB_ODATA_SERVER env override so ops can pin the access URL
     shown in the Geotab Data Connector add-in.
  2. Otherwise starts at Geotab's unified Data Connector URL and follows the
     redirect to the database's current federation server while preserving auth.
  3. Falls back to numbered odata-connector-{1..15} hosts and validates each
     with an actual table query, not a bare metadata request.
  4. Treats any 406 response from a downstream call as a cache poison signal:
     invalidates the cached server and retries discovery once.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from fastapi import APIRouter, HTTPException, Query

from _cache import clear_cached_prefix, get_cached, set_cached
from geotab_client import GeotabClient

logger = logging.getLogger(__name__)
router = APIRouter()

# OData base – prefer Geotab's unified endpoint because it redirects to the
# database's current Data Connector server. Numbered hosts remain as fallback
# for pinned Tableau-style access URLs and older environments.
_ODATA_SERVER: str | None = None
_ODATA_UNIFIED_SERVER = "https://data-connector.geotab.com/odata/v4/svc/"
_ODATA_SERVERS = [f"https://odata-connector-{i}.geotab.com/odata/v4/svc/" for i in range(1, 16)]
_ODATA_DISCOVERY_SERVERS = [_ODATA_UNIFIED_SERVER, *_ODATA_SERVERS]
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_KM_TO_MILES = 0.621371
try:
    _ODATA_MAX_CONCURRENT_REQUESTS = max(
        int(os.getenv("FLEETPULSE_DATA_CONNECTOR_MAX_CONCURRENT_REQUESTS", "6")),
        1,
    )
except ValueError:
    _ODATA_MAX_CONCURRENT_REQUESTS = 6
try:
    _ODATA_REQUEST_TIMEOUT_SECONDS = max(
        float(os.getenv("FLEETPULSE_DATA_CONNECTOR_TIMEOUT_SECONDS", "20")),
        1.0,
    )
except ValueError:
    _ODATA_REQUEST_TIMEOUT_SECONDS = 20.0
try:
    _ODATA_RETRY_COUNT = max(
        int(os.getenv("FLEETPULSE_DATA_CONNECTOR_RETRY_COUNT", "1")),
        0,
    )
except ValueError:
    _ODATA_RETRY_COUNT = 1
try:
    _ODATA_QUEUE_TIMEOUT_SECONDS = max(
        float(os.getenv("FLEETPULSE_DATA_CONNECTOR_QUEUE_TIMEOUT_SECONDS", "5")),
        0.1,
    )
except ValueError:
    _ODATA_QUEUE_TIMEOUT_SECONDS = 5.0
try:
    _DATA_CONNECTOR_CACHE_TTL_SECONDS = max(
        int(os.getenv("FLEETPULSE_DATA_CONNECTOR_CACHE_TTL_SECONDS", "300")),
        0,
    )
except ValueError:
    _DATA_CONNECTOR_CACHE_TTL_SECONDS = 300
_ODATA_REQUEST_SEMAPHORE = asyncio.Semaphore(_ODATA_MAX_CONCURRENT_REQUESTS)

# Probe table that exists for every K1 database and is cheap to query.
_PROBE_TABLE = "LatestVehicleMetadata"
_VEHICLE_ID_FIELDS = (
    "DeviceId",
    "DeviceID",
    "VehicleId",
    "VehicleID",
    "AssetId",
    "AssetID",
    "Id",
    "id",
    "SerialNo",
    "SerialNumber",
    "DeviceSerialNumber",
)
_VEHICLE_KPI_LABEL_FIELDS = (
    "VehicleName",
    "DeviceName",
    "Name",
    "AssetName",
    "AssetNumber",
    "UnitNumber",
    "UnitNo",
    "Unit",
    "Number",
)
_VEHICLE_METADATA_LABEL_FIELDS = (
    "Name",
    "DeviceName",
    "VehicleName",
    "AssetName",
    "AssetNumber",
    "UnitNumber",
    "UnitNo",
    "Unit",
    "Number",
)


def _basic_auth() -> tuple[str, str]:
    gc = GeotabClient.get()
    username = _odata_auth_username(gc.database, gc.username)
    password = gc.password
    return (username, password)


def _odata_auth_username(database: str | None, username: str | None) -> str:
    """Return the Basic auth username Geotab Data Connector expects.

    OData requires "<database>/<username>". Some deployments accidentally store
    the already-prefixed value in GEOTAB_USERNAME; preserve that shape instead
    of producing "<database>/<database>/<username>".
    """
    db = str(database or "").strip().strip("/")
    user = str(username or "").strip()
    if "/" in user:
        return user
    if not db:
        return user
    return f"{db}/{user}"


def _data_connector_config_status() -> dict[str, Any]:
    gc = GeotabClient.get()
    auth_username = _odata_auth_username(gc.database, gc.username)
    database_prefix = auth_username.split("/", 1)[0] if "/" in auth_username else ""
    pinned_server = os.environ.get("GEOTAB_ODATA_SERVER", "").strip()
    return {
        "database_configured": bool(str(gc.database or "").strip()),
        "username_configured": bool(str(gc.username or "").strip()),
        "password_configured": bool(str(gc.password or "").strip()),
        "geotab_server_configured": bool(str(gc.server or "").strip()),
        "basic_auth_username_has_database_prefix": bool(database_prefix),
        "basic_auth_username_format": (
            "<database>/<username>"
            if database_prefix
            else "missing_database_prefix"
        ),
        "basic_auth_database_matches_env": (
            not database_prefix
            or database_prefix.casefold() == str(gc.database or "").strip().strip("/").casefold()
        ),
        "odata_server_pinned": bool(pinned_server),
        "odata_server": _normalize_server(pinned_server) if pinned_server else None,
        "cached_odata_server": _ODATA_SERVER,
        "probe_table": _PROBE_TABLE,
    }


def _cache_key(*parts: object) -> str:
    return "data-connector:" + ":".join(str(part) for part in parts)


def _get_data_connector_cached(key: str) -> Any | None:
    if _DATA_CONNECTOR_CACHE_TTL_SECONDS <= 0:
        return None
    return get_cached(key, ttl=_DATA_CONNECTOR_CACHE_TTL_SECONDS)


def _set_data_connector_cached(key: str, value: Any) -> Any:
    if _DATA_CONNECTOR_CACHE_TTL_SECONDS > 0:
        set_cached(key, value)
    return value


def _is_jurisdiction_error(text: str) -> bool:
    return "Jurisdiction Mismatch" in (text or "")


def _is_missing_metadata_error(text: str) -> bool:
    return "Metadata is Not Found" in (text or "")


def _normalize_server(url: str) -> str:
    url = url.strip()
    base = _odata_base_from_url(url)
    if base:
        return base
    return url if url.endswith("/") else f"{url}/"


def _odata_base_from_url(url: str) -> str | None:
    """Extract the OData service root from a redirected table URL."""
    parsed = urlparse(url)
    marker = "/odata/v4/svc/"
    if marker not in parsed.path:
        return None
    end = parsed.path.index(marker) + len(marker)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path[:end], "", "", ""))


def _auth_failed_detail() -> str:
    return (
        "Data Connector authentication failed. Confirm GEOTAB_DATABASE, "
        "GEOTAB_USERNAME, and GEOTAB_PASSWORD are set, and use the Basic auth "
        "username format '<database>/<username>'."
    )


async def _probe_server(client: httpx.AsyncClient, url: str, auth: tuple[str, str]) -> str | None:
    """Return the service root only if it can actually return rows for our DB."""
    try:
        r = await client.get(
            f"{url}{_PROBE_TABLE}",
            auth=auth,
            params={"$search": "last_1_day", "$top": "1"},
            timeout=10,
            follow_redirects=False,
        )
    except Exception as exc:
        logger.debug("probe %s failed: %s", url, exc)
        return None
    if r.status_code in _REDIRECT_STATUSES:
        location = r.headers.get("location")
        if not location:
            return None
        redirected_url = urljoin(str(r.request.url), location)
        redirected_base = _odata_base_from_url(redirected_url)
        if not redirected_base or redirected_base == url:
            return None
        return await _probe_server(client, redirected_base, auth)
    if r.status_code == 200:
        return url
    if r.status_code == 401:
        raise HTTPException(401, _auth_failed_detail())
    if r.status_code == 412:
        raise HTTPException(
            412,
            "Data Connector not activated. Install the add-in in MyGeotab "
            "Administration > System Settings > Add-Ins.",
        )
    if r.status_code == 429:
        raise HTTPException(
            429,
            "Data Connector rate limit reached while discovering the server. "
            "Wait a few minutes before refreshing.",
        )
    if _is_jurisdiction_error(r.text):
        logger.info("probe %s rejected (Jurisdiction Mismatch)", url)
    else:
        logger.info("probe %s rejected status=%s", url, r.status_code)
    return None


async def _find_server(force_refresh: bool = False) -> str:
    global _ODATA_SERVER
    if _ODATA_SERVER and not force_refresh:
        return _ODATA_SERVER

    # Explicit override via env var (preferred path for production).
    pinned = os.environ.get("GEOTAB_ODATA_SERVER", "").strip()
    if pinned:
        pinned = _normalize_server(pinned)
        _ODATA_SERVER = pinned
        logger.info("GEOTAB_ODATA_SERVER pinned to %s", pinned)
        return pinned

    auth = _basic_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        for url in _ODATA_DISCOVERY_SERVERS:
            discovered = await _probe_server(client, url, auth)
            if discovered:
                _ODATA_SERVER = discovered
                logger.info("Data Connector server discovered: %s", discovered)
                return discovered
    raise HTTPException(
        503,
        "Could not find a Data Connector server that accepts this Geotab database. "
        "Set GEOTAB_ODATA_SERVER to the access URL shown in the Geotab Data "
        "Connector add-in, or have a Geotab admin reissue the OData connector "
        "for the database's current federation server.",
    )


async def _invalidate_server() -> None:
    global _ODATA_SERVER
    if _ODATA_SERVER:
        logger.warning("Invalidating cached Data Connector server %s", _ODATA_SERVER)
    _ODATA_SERVER = None
    clear_cached_prefix("data-connector:")


async def _acquire_odata_slot(table: str) -> None:
    try:
        await asyncio.wait_for(
            _ODATA_REQUEST_SEMAPHORE.acquire(),
            timeout=_ODATA_QUEUE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            503,
            f"Data Connector is busy while reading {table}; retry shortly.",
        ) from exc


async def _odata_get(table: str, search: str = "last_14_day", select: str | None = None, top: int = 1000) -> list[dict]:
    base = await _find_server()
    auth = _basic_auth()

    async def _do_get(target_base: str) -> list[dict]:
        global _ODATA_SERVER
        params: dict[str, Any] = {"$search": search, "$top": str(top)}
        if select:
            params["$select"] = select
        url = f"{target_base}{table}"
        results: list[dict] = []
        redirects_remaining = 3
        async with httpx.AsyncClient(timeout=_ODATA_REQUEST_TIMEOUT_SECONDS) as client:
            while url:
                last_timeout: Exception | None = None
                for attempt in range(_ODATA_RETRY_COUNT + 1):
                    try:
                        await _acquire_odata_slot(table)
                        try:
                            r = await asyncio.wait_for(
                                client.get(
                                    url,
                                    auth=auth,
                                    params=params if url.startswith(target_base) else None,
                                    follow_redirects=False,
                                ),
                                timeout=_ODATA_REQUEST_TIMEOUT_SECONDS + 2,
                            )
                        finally:
                            _ODATA_REQUEST_SEMAPHORE.release()
                        break
                    except HTTPException:
                        raise
                    except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
                        last_timeout = exc
                        if attempt < _ODATA_RETRY_COUNT:
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        raise HTTPException(
                            504,
                            f"Data Connector timeout while reading {table}.",
                        ) from exc
                    except httpx.HTTPError as exc:
                        raise HTTPException(
                            502,
                            f"Data Connector network error while reading {table}: {type(exc).__name__}",
                        ) from exc
                    except Exception as exc:
                        raise HTTPException(
                            502,
                            f"Data Connector unexpected error while reading {table}: {type(exc).__name__}",
                        ) from exc
                else:  # pragma: no cover - loop always breaks or raises.
                    raise HTTPException(
                        504,
                        f"Data Connector timeout while reading {table}: {type(last_timeout).__name__}",
                    )
                if r.status_code in _REDIRECT_STATUSES:
                    location = r.headers.get("location")
                    if not location or redirects_remaining <= 0:
                        raise HTTPException(r.status_code, "Data Connector redirect could not be followed.")
                    url = urljoin(str(r.request.url), location)
                    redirected_base = _odata_base_from_url(url)
                    if redirected_base:
                        target_base = redirected_base
                        _ODATA_SERVER = redirected_base
                    params = {}
                    redirects_remaining -= 1
                    continue
                redirects_remaining = 3
                if r.status_code == 401:
                    raise HTTPException(401, _auth_failed_detail())
                if r.status_code == 412:
                    raise HTTPException(
                        412,
                        "Data Connector not activated. Install the add-in in MyGeotab "
                        "Administration > System Settings > Add-Ins.",
                    )
                if r.status_code == 406 and _is_jurisdiction_error(r.text):
                    # Signal jurisdiction failure to caller for retry handling.
                    raise _JurisdictionMismatch(r.text[:500])
                if r.status_code != 200:
                    raise HTTPException(
                        r.status_code, f"Data Connector error: {r.text[:500]}"
                    )
                data = r.json()
                results.extend(data.get("value", []))
                url = data.get("@odata.nextLink")
                params = {}  # nextLink includes params
        return results

    try:
        return await _do_get(base)
    except _JurisdictionMismatch:
        # Cache poisoned. Invalidate, refresh, retry exactly once.
        await _invalidate_server()
        try:
            base2 = await _find_server(force_refresh=True)
        except HTTPException:
            raise HTTPException(
                406,
                "Data Connector error: Jurisdiction Mismatch. The Geotab OData "
                "connector for this database needs to be reissued for its current "
                "federation server. Set GEOTAB_ODATA_SERVER once the correct server "
                "is known.",
            )
        try:
            return await _do_get(base2)
        except _JurisdictionMismatch as exc:
            raise HTTPException(
                406,
                f"Data Connector error: Jurisdiction Mismatch persists after refresh: {exc.detail}",
            )


async def _cached_odata_get(
    table: str,
    search: str = "last_14_day",
    select: str | None = None,
    top: int = 1000,
) -> list[dict]:
    cache_key = _cache_key("odata", table, search, select or "", top)
    cached = _get_data_connector_cached(cache_key)
    if cached is not None:
        return cached
    rows = await _odata_get(table, search=search, select=select, top=top)
    return _set_data_connector_cached(cache_key, rows)


def _connector_error_message(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        return detail if isinstance(detail, str) else str(detail)
    return f"{type(exc).__name__}: {exc}"


def _degraded_source_payload(days: int, exc: Exception) -> dict[str, Any]:
    return {
        "period_days": days,
        "feed_status": "degraded",
        "source_authority": "K1 Logistics Inc / Geotab Data Connector",
        "projection_mode": "read_only",
        "message": _connector_error_message(exc),
    }


class _JurisdictionMismatch(Exception):
    """Internal signal: upstream returned 406 Jurisdiction Mismatch."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@router.get("/status")
async def data_connector_status():
    """Return sanitized Data Connector readiness details without secrets."""
    return _data_connector_config_status()


def _number(row: dict, *names: str) -> float:
    for name in names:
        value = row.get(name)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _optional_number(row: dict, *names: str) -> float | None:
    for name in names:
        value = row.get(name)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _text(row: dict, *names: str) -> str | None:
    for name in names:
        value = row.get(name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _lookup_key(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text.casefold() if text else None


def _vehicle_lookup_values(row: dict) -> list[str]:
    values: list[str] = []
    for field in (*_VEHICLE_ID_FIELDS, *_VEHICLE_KPI_LABEL_FIELDS):
        value = _text(row, field)
        if value and value not in values:
            values.append(value)
    return values


def _vehicle_metadata_display_name(row: dict) -> str | None:
    id_keys = {
        key
        for key in (_lookup_key(_text(row, field)) for field in _VEHICLE_ID_FIELDS)
        if key
    }
    fallback: str | None = None
    for field in _VEHICLE_METADATA_LABEL_FIELDS:
        value = _text(row, field)
        if not value:
            continue
        fallback = fallback or value
        if _lookup_key(value) not in id_keys:
            return value
    return fallback


def _vehicle_metadata_name_map(rows: list[dict]) -> dict[str, str]:
    name_map: dict[str, str] = {}
    for row in rows:
        display_name = _vehicle_metadata_display_name(row)
        if not display_name:
            continue
        for value in _vehicle_lookup_values(row):
            key = _lookup_key(value)
            if key and key not in name_map:
                name_map[key] = display_name
    return name_map


def _vehicle_kpi_identity(row: dict) -> str:
    return (
        _text(row, *_VEHICLE_ID_FIELDS)
        or _text(row, *_VEHICLE_KPI_LABEL_FIELDS)
        or "unknown"
    )


def _vehicle_display_name(row: dict, vehicle_names: dict[str, str]) -> str:
    for value in _vehicle_lookup_values(row):
        key = _lookup_key(value)
        if key and key in vehicle_names:
            return vehicle_names[key]
    return _text(row, *_VEHICLE_KPI_LABEL_FIELDS, *_VEHICLE_ID_FIELDS) or "unknown"


def _should_replace_vehicle_name(current: str | None, candidate: str, vehicle_id: str) -> bool:
    if not current:
        return True
    current_key = _lookup_key(current)
    vehicle_key = _lookup_key(vehicle_id)
    candidate_key = _lookup_key(candidate)
    return current_key in {None, "unknown", vehicle_key} and candidate_key not in {
        None,
        "unknown",
    }


def _aggregate_vehicle_kpis(rows: list[dict], vehicle_names: dict[str, str] | None = None) -> list[dict]:
    from collections import defaultdict

    vehicle_names = vehicle_names or {}
    agg: dict[str, dict] = defaultdict(
        lambda: {
            "vehicle_id": "unknown",
            "vehicle_name": "unknown",
            "distance_miles": 0.0,
            "drive_hours": 0.0,
            "idle_hours": 0.0,
            "trips": 0,
            "fuel_litres": 0.0,
        }
    )
    for row in rows:
        vehicle_id = _vehicle_kpi_identity(row)
        item = agg[vehicle_id]
        item["vehicle_id"] = vehicle_id
        display_name = _vehicle_display_name(row, vehicle_names)
        if _should_replace_vehicle_name(item.get("vehicle_name"), display_name, vehicle_id):
            item["vehicle_name"] = display_name
        source_distance_km = _number(row, "Distance_Km", "GPS_Distance_Km", "TotalDistance_Km")
        item["distance_miles"] += source_distance_km * _KM_TO_MILES
        item["drive_hours"] += _number(row, "DriveDuration_Seconds") / 3600
        item["drive_hours"] += _number(row, "TotalDriveTime_Hours")
        item["idle_hours"] += _number(row, "IdleDuration_Seconds") / 3600
        item["idle_hours"] += _number(row, "TotalIdleTime_Hours")
        item["trips"] += int(_number(row, "Trip_Count", "TotalTrips"))
        item["fuel_litres"] += _number(row, "TotalFuel_Litres", "Fuel_Litres")

    return sorted(agg.values(), key=lambda vehicle: vehicle["distance_miles"], reverse=True)


def _convert_trip_summary_rows(rows: list[dict]) -> list[dict]:
    converted: list[dict] = []
    for row in rows:
        item = dict(row)
        source_distance_km = _number(item, "TotalDistance_Km", "Distance_Km", "GPS_Distance_Km")
        item["total_distance_miles"] = source_distance_km * _KM_TO_MILES
        item.pop("TotalDistance_Km", None)
        item.pop("Distance_Km", None)
        item.pop("GPS_Distance_Km", None)
        converted.append(item)
    return converted


def _fault_vehicle_identity(row: dict) -> str:
    return _vehicle_kpi_identity(row)


def _fault_code(row: dict) -> str | None:
    return _text(row, "FaultCode", "DiagnosticName", "FaultCodeDescription", "DiagnosticId")


def _fault_count(row: dict) -> int:
    return max(
        int(_number(row, "Count", "FaultCount", "Count_Daily", "EventCount") or 1),
        1,
    )


def _fault_date(row: dict) -> str | None:
    value = _text(row, "Date", "Day", "Local_Date", "AnyStatesDateTimeFirstSeen")
    return value[:10] if value else None


def _safety_date(row: dict) -> str | None:
    value = _text(row, "Date", "Day", "Local_Date")
    return value[:10] if value else None


def _rank_percent(value: float | None) -> float | None:
    if value is None:
        return None
    percent = value * 100 if 0 <= value <= 1 else value
    return round(percent, 1)


def _latest_safety_row(rows: list[dict]) -> dict | None:
    usable = [row for row in rows if _safety_date(row)]
    if not usable:
        return rows[-1] if rows else None
    return max(usable, key=lambda row: _safety_date(row) or "")


def _safety_rank_value(row: dict) -> float | None:
    return _optional_number(row, "Safety_Rank", "SafetyRank", "SafetyScore", "Safety_Score")


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _safety_summary(fleet_rows: list[dict], vehicle_rows: list[dict]) -> dict[str, Any]:
    latest = _latest_safety_row(fleet_rows)
    safety_rank_values = [
        rank for row in fleet_rows if (rank := _safety_rank_value(row)) is not None
    ]
    safety_rank_pct = _rank_percent(_average(safety_rank_values))
    latest_safety_rank_pct = None
    predicted_collisions = None
    predicted_collision_values = [
        value
        for row in fleet_rows
        if (
            value := _optional_number(
                row,
                "PredictedCollisionsPer1MillionM",
                "PredictedCollisionsPer1MillionMi",
                "PredictedCollisionsPer1MillionMiles",
            )
        )
        is not None
    ]
    collision_values = [
        value
        for row in fleet_rows
        if (value := _optional_number(row, "TotalCollisionCount_Daily", "CollisionCount")) is not None
    ]
    collision_count = int(sum(collision_values)) if collision_values else None
    latest_date = None
    dated_rows = sorted(
        [(date, row) for row in fleet_rows if (date := _safety_date(row))],
        key=lambda item: item[0],
    )
    period_start_date = dated_rows[0][0] if dated_rows else None
    period_end_date = dated_rows[-1][0] if dated_rows else None

    if latest:
        latest_date = _safety_date(latest)
        latest_safety_rank_pct = _rank_percent(_safety_rank_value(latest))
    predicted_collisions = _average(predicted_collision_values)

    return {
        "safety_rank_pct": safety_rank_pct,
        "latest_safety_rank_pct": latest_safety_rank_pct,
        "latest_date": latest_date,
        "period_start_date": period_start_date,
        "period_end_date": period_end_date,
        "fleet_row_count": len(fleet_rows),
        "vehicle_score_count": len(vehicle_rows),
        "total_collision_count": collision_count,
        "predicted_collisions_per_1m_miles": (
            round(predicted_collisions, 3) if predicted_collisions is not None else None
        ),
        "calculation": "average_fleet_daily_safety_rank",
    }


def _annotate_fault_rows(rows: list[dict], vehicle_names: dict[str, str] | None = None) -> list[dict]:
    vehicle_names = vehicle_names or {}
    annotated: list[dict] = []
    for row in rows:
        source_vehicle_id = _fault_vehicle_identity(row)
        vehicle_name = _vehicle_display_name(row, vehicle_names)
        item = dict(row)
        item["source_vehicle_id"] = source_vehicle_id
        item["vehicle_id"] = source_vehicle_id
        item["vehicle_name"] = vehicle_name
        item["fault_code"] = _fault_code(row)
        item["count"] = _fault_count(row)
        item["date"] = _fault_date(row)
        annotated.append(item)
    return annotated


@router.get("/tables")
async def list_tables():
    """List available Data Connector tables.

    Note: a 200 response from this metadata endpoint does NOT prove the
    chosen federation server matches our database's jurisdiction. Use this
    only to enumerate table names; rely on actual table queries (with proper
    jurisdiction handling in _odata_get) for data.
    """
    cache_key = _cache_key("tables")
    cached = _get_data_connector_cached(cache_key)
    if cached is not None:
        return cached
    base = await _find_server()
    auth = _basic_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(base, auth=auth)
        if r.status_code != 200:
            raise HTTPException(r.status_code, r.text[:500])
        return _set_data_connector_cached(cache_key, r.json())


@router.get("/vehicle-kpis")
async def vehicle_kpis(days: int = Query(14, ge=1, le=90)):
    """Fleet utilization KPIs per vehicle."""
    cache_key = _cache_key("vehicle-kpis", days)
    cached = _get_data_connector_cached(cache_key)
    if cached is not None:
        return cached
    search = f"last_{days}_day" if days in (1, 7, 14, 30, 90) else "last_14_day"
    try:
        rows = await _cached_odata_get("VehicleKpi_Daily", search=search)
    except Exception as exc:
        logger.warning("VehicleKpi_Daily unavailable: %s", _connector_error_message(exc))
        return {
            "vehicles": [],
            "summary": {
                "total_vehicles": 0,
                "total_distance_miles": 0,
                "total_drive_hours": 0,
                "total_idle_hours": 0,
                "utilization_pct": 0,
            },
            **_degraded_source_payload(days, exc),
        }
    if not rows:
        return _set_data_connector_cached(cache_key, {
            "vehicles": [],
            "summary": {
                "total_vehicles": 0,
                "total_distance_miles": 0,
                "total_drive_hours": 0,
                "total_idle_hours": 0,
                "utilization_pct": 0,
            },
            "period_days": days,
            "feed_status": "empty",
            "source_authority": "K1 Logistics Inc / Geotab Data Connector",
            "projection_mode": "read_only",
        })

    try:
        metadata_rows = await _cached_odata_get(_PROBE_TABLE, search=search, top=2000)
    except HTTPException as exc:
        logger.warning(
            "Vehicle metadata lookup failed; falling back to KPI identifiers: status=%s",
            exc.status_code,
        )
        metadata_rows = []

    vehicles = _aggregate_vehicle_kpis(rows, _vehicle_metadata_name_map(metadata_rows))
    total_dist = sum(v["distance_miles"] for v in vehicles)
    total_drive = sum(v["drive_hours"] for v in vehicles)
    total_idle = sum(v["idle_hours"] for v in vehicles)

    return _set_data_connector_cached(cache_key, {
        "vehicles": vehicles,
        "summary": {
            "total_vehicles": len(vehicles),
            "total_distance_miles": round(total_dist, 1),
            "total_drive_hours": round(total_drive, 1),
            "total_idle_hours": round(total_idle, 1),
            "utilization_pct": round(total_drive / (total_drive + total_idle) * 100, 1) if (total_drive + total_idle) > 0 else 0,
        },
        "period_days": days,
        "feed_status": "ok",
    })


@router.get("/safety-scores")
async def safety_scores(days: int = Query(14, ge=1, le=90)):
    """Aggregated safety scores from Data Connector."""
    cache_key = _cache_key("safety-scores", days)
    cached = _get_data_connector_cached(cache_key)
    if cached is not None:
        return cached
    search = f"last_{days}_day" if days in (1, 7, 14, 30, 90) else "last_14_day"

    # Try fleet-level first, then vehicle-level
    try:
        fleet_rows, vehicle_rows = await asyncio.gather(
            _cached_odata_get("FleetSafety_Daily", search=search),
            _cached_odata_get("VehicleSafety_Daily", search=search),
        )
    except Exception as exc:
        logger.warning("Safety Data Connector rows unavailable: %s", _connector_error_message(exc))
        return {
            "fleet_daily": [],
            "vehicle_scores": [],
            "summary": _safety_summary([], []),
            **_degraded_source_payload(days, exc),
        }

    return _set_data_connector_cached(cache_key, {
        "fleet_daily": fleet_rows[:30],
        "vehicle_scores": vehicle_rows[:100],
        "summary": _safety_summary(fleet_rows, vehicle_rows),
        "period_days": days,
        "feed_status": "ok",
        "source_authority": "K1 Logistics Inc / Geotab Data Connector",
        "projection_mode": "read_only",
    })


@router.get("/fault-trends")
async def fault_trends(days: int = Query(14, ge=1, le=90)):
    """Fault code trends from Data Connector."""
    cache_key = _cache_key("fault-trends", days)
    cached = _get_data_connector_cached(cache_key)
    if cached is not None:
        return cached
    search = f"last_{days}_day" if days in (1, 7, 14, 30, 90) else "last_14_day"
    try:
        rows = await _cached_odata_get("FaultMonitoring_Daily", search=search)
    except HTTPException as exc:
        if exc.status_code == 404 and _is_missing_metadata_error(str(exc.detail)):
            logger.warning("FaultMonitoring_Daily is not available in this Data Connector feed")
            return _set_data_connector_cached(cache_key, {
                "faults": [],
                "period_days": days,
                "feed_status": "table_unavailable",
                "message": "FaultMonitoring_Daily is not available for this Geotab Data Connector feed.",
            })
        logger.warning("FaultMonitoring_Daily unavailable: %s", _connector_error_message(exc))
        return {
            "faults": [],
            **_degraded_source_payload(days, exc),
        }
    except Exception as exc:
        logger.warning("FaultMonitoring_Daily unavailable: %s", _connector_error_message(exc))
        return {
            "faults": [],
            **_degraded_source_payload(days, exc),
        }

    try:
        metadata_rows = await _cached_odata_get(_PROBE_TABLE, search=search, top=2000)
    except HTTPException as exc:
        logger.warning(
            "Fault trend vehicle metadata lookup failed; falling back to fault identifiers: status=%s",
            exc.status_code,
        )
        metadata_rows = []

    faults = _annotate_fault_rows(rows[:200], _vehicle_metadata_name_map(metadata_rows))
    return _set_data_connector_cached(cache_key, {"faults": faults, "period_days": days, "feed_status": "ok"})


@router.get("/trip-summary")
async def trip_summary(days: int = Query(14, ge=1, le=90)):
    """Trip summaries from Data Connector."""
    cache_key = _cache_key("trip-summary", days)
    cached = _get_data_connector_cached(cache_key)
    if cached is not None:
        return cached
    search = f"last_{days}_day" if days in (1, 7, 14, 30, 90) else "last_14_day"
    rows = await _cached_odata_get("VehicleKpi_Daily", search=search)
    return _set_data_connector_cached(
        cache_key,
        {"trips": _convert_trip_summary_rows(rows[:200]), "period_days": days},
    )
