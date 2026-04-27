"""Data Connector endpoints – pre-aggregated fleet KPIs via Geotab OData.

Fix 2026-04-27: the previous auto-discovery probed every odata-connector-{1..7}
with a bare metadata GET and cached the FIRST one to return 200. Servers
respond 200 to bare metadata regardless of jurisdiction, so the wrong server
often got cached. Subsequent table queries then returned
HTTP 406 "Jurisdiction Mismatch" until the worker recycled.

This revision:
  1. Honors a GEOTAB_ODATA_SERVER env override so ops can pin the correct
     server explicitly (preferred path).
  2. Probes with an actual table query (LatestVehicleMetadata?$top=1) when
     auto-discovering, so jurisdiction is validated up front.
  3. Treats any 406 response from a downstream call as a cache poison signal:
     invalidates the cached server and retries the discovery once.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from geotab_client import GeotabClient

logger = logging.getLogger(__name__)
router = APIRouter()

# OData base – we try servers 1-15, cache the working one (Geotab has been
# expanding the federation pool; bumping the upper bound is cheap).
_ODATA_SERVER: str | None = None
_ODATA_SERVERS = [f"https://odata-connector-{i}.geotab.com/odata/v4/svc/" for i in range(1, 16)]

# Probe table that exists for every K1 database and is cheap to query.
_PROBE_TABLE = "LatestVehicleMetadata"


def _basic_auth() -> tuple[str, str]:
    gc = GeotabClient.get()
    username = f"{gc.database}/{gc.username}"
    password = gc.password
    return (username, password)


def _is_jurisdiction_error(text: str) -> bool:
    return "Jurisdiction Mismatch" in (text or "")


async def _probe_server(client: httpx.AsyncClient, url: str, auth: tuple[str, str]) -> bool:
    """Return True only if this server can actually return rows for our DB."""
    try:
        r = await client.get(
            f"{url}{_PROBE_TABLE}",
            auth=auth,
            params={"$search": "last_1_day", "$top": "1"},
            timeout=10,
        )
    except Exception as exc:
        logger.debug("probe %s failed: %s", url, exc)
        return False
    if r.status_code == 200:
        return True
    if _is_jurisdiction_error(r.text):
        logger.info("probe %s rejected (Jurisdiction Mismatch)", url)
    else:
        logger.info("probe %s rejected status=%s", url, r.status_code)
    return False


async def _find_server(force_refresh: bool = False) -> str:
    global _ODATA_SERVER
    if _ODATA_SERVER and not force_refresh:
        return _ODATA_SERVER

    # Explicit override via env var (preferred path for production).
    pinned = os.environ.get("GEOTAB_ODATA_SERVER", "").strip()
    if pinned:
        if not pinned.endswith("/"):
            pinned += "/"
        _ODATA_SERVER = pinned
        logger.info("GEOTAB_ODATA_SERVER pinned to %s", pinned)
        return pinned

    auth = _basic_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        for url in _ODATA_SERVERS:
            if await _probe_server(client, url, auth):
                _ODATA_SERVER = url
                logger.info("Data Connector server discovered: %s", url)
                return url
    raise HTTPException(
        503,
        "Could not find a Data Connector server that accepts this Geotab database. "
        "Either set GEOTAB_ODATA_SERVER explicitly or have a Geotab admin reissue "
        "the OData connector for the database's current federation server.",
    )


async def _invalidate_server() -> None:
    global _ODATA_SERVER
    if _ODATA_SERVER:
        logger.warning("Invalidating cached Data Connector server %s", _ODATA_SERVER)
    _ODATA_SERVER = None


async def _odata_get(table: str, search: str = "last_14_day", select: str | None = None, top: int = 1000) -> list[dict]:
    base = await _find_server()
    auth = _basic_auth()

    async def _do_get(target_base: str) -> list[dict]:
        params: dict[str, Any] = {"$search": search, "$top": str(top)}
        if select:
            params["$select"] = select
        url = f"{target_base}{table}"
        results: list[dict] = []
        async with httpx.AsyncClient(timeout=30) as client:
            while url:
                r = await client.get(
                    url,
                    auth=auth,
                    params=params if url.startswith(target_base) else None,
                )
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


class _JurisdictionMismatch(Exception):
    """Internal signal: upstream returned 406 Jurisdiction Mismatch."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@router.get("/tables")
async def list_tables():
    """List available Data Connector tables.

    Note: a 200 response from this metadata endpoint does NOT prove the
    chosen federation server matches our database's jurisdiction. Use this
    only to enumerate table names; rely on actual table queries (with proper
    jurisdiction handling in _odata_get) for data.
    """
    base = await _find_server()
    auth = _basic_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(base, auth=auth)
        if r.status_code != 200:
            raise HTTPException(r.status_code, r.text[:500])
        return r.json()


@router.get("/vehicle-kpis")
async def vehicle_kpis(days: int = Query(14, ge=1, le=90)):
    """Fleet utilization KPIs per vehicle."""
    search = f"last_{days}_day" if days in (1, 7, 14, 30, 90) else "last_14_day"
    rows = await _odata_get("VehicleKpi_Daily", search=search)
    if not rows:
        return {"vehicles": [], "summary": {}}

    # Aggregate per vehicle
    from collections import defaultdict
    agg: dict[str, dict] = defaultdict(lambda: {
        "distance_km": 0, "drive_hours": 0, "idle_hours": 0, "trips": 0, "fuel_litres": 0
    })
    for r in rows:
        vid = r.get("DeviceSerialNumber") or r.get("VehicleName") or r.get("DeviceId", "unknown")
        a = agg[vid]
        a["vehicle_name"] = r.get("VehicleName", vid)
        a["distance_km"] += r.get("TotalDistance_Km", 0) or 0
        a["drive_hours"] += r.get("TotalDriveTime_Hours", 0) or 0
        a["idle_hours"] += r.get("TotalIdleTime_Hours", 0) or 0
        a["trips"] += r.get("TotalTrips", 0) or 0
        a["fuel_litres"] += r.get("TotalFuel_Litres", 0) or 0

    vehicles = sorted(agg.values(), key=lambda v: v["distance_km"], reverse=True)
    total_dist = sum(v["distance_km"] for v in vehicles)
    total_drive = sum(v["drive_hours"] for v in vehicles)
    total_idle = sum(v["idle_hours"] for v in vehicles)

    return {
        "vehicles": vehicles,
        "summary": {
            "total_vehicles": len(vehicles),
            "total_distance_km": round(total_dist, 1),
            "total_drive_hours": round(total_drive, 1),
            "total_idle_hours": round(total_idle, 1),
            "utilization_pct": round(total_drive / (total_drive + total_idle) * 100, 1) if (total_drive + total_idle) > 0 else 0,
        },
        "period_days": days,
    }


@router.get("/safety-scores")
async def safety_scores(days: int = Query(14, ge=1, le=90)):
    """Aggregated safety scores from Data Connector."""
    search = f"last_{days}_day" if days in (1, 7, 14, 30, 90) else "last_14_day"

    # Try fleet-level first, then vehicle-level
    fleet_rows = await _odata_get("FleetSafety_Daily", search=search)
    vehicle_rows = await _odata_get("VehicleSafety_Daily", search=search)

    return {
        "fleet_daily": fleet_rows[:30],
        "vehicle_scores": vehicle_rows[:100],
        "period_days": days,
    }


@router.get("/fault-trends")
async def fault_trends(days: int = Query(14, ge=1, le=90)):
    """Fault code trends from Data Connector."""
    search = f"last_{days}_day" if days in (1, 7, 14, 30, 90) else "last_14_day"
    rows = await _odata_get("FaultCode_Daily", search=search)
    return {"faults": rows[:200], "period_days": days}


@router.get("/trip-summary")
async def trip_summary(days: int = Query(14, ge=1, le=90)):
    """Trip summaries from Data Connector."""
    search = f"last_{days}_day" if days in (1, 7, 14, 30, 90) else "last_14_day"
    rows = await _odata_get("VehicleKpi_Daily", search=search,
                            select="VehicleName,TotalTrips,TotalDistance_Km,TotalDriveTime_Hours,TotalFuel_Litres")
    return {"trips": rows[:200], "period_days": days}
