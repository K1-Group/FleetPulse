"""Data Connector endpoints – pre-aggregated fleet KPIs via Geotab OData.

Demo mode: when the real Geotab OData server is unreachable or the add-in is not
activated (HTTP 503 / 412), every endpoint falls back to seeded mock data so the
UI is always functional without a live Geotab subscription.
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from geotab_client import GeotabClient

router = APIRouter()

# OData base – we try servers 1-7, cache the working one
_ODATA_SERVER: str | None = None
_ODATA_SERVERS = [f"https://odata-connector-{i}.geotab.com/odata/v4/svc/" for i in range(1, 8)]


def _basic_auth() -> tuple[str, str]:
    gc = GeotabClient.get()
    username = f"{gc.database}/{gc.username}"
    password = gc.password
    return (username, password)


async def _find_server() -> str:
    global _ODATA_SERVER
    if _ODATA_SERVER:
        return _ODATA_SERVER
    auth = _basic_auth()
    async with httpx.AsyncClient(timeout=10) as client:
        for url in _ODATA_SERVERS:
            try:
                r = await client.get(url, auth=auth)
                if r.status_code == 200:
                    _ODATA_SERVER = url
                    return url
            except Exception:
                continue
    raise HTTPException(503, "Could not connect to any Data Connector server")


async def _odata_get(table: str, search: str = "last_14_day", select: str | None = None, top: int = 1000) -> list[dict]:
    base = await _find_server()
    auth = _basic_auth()
    params: dict[str, Any] = {"$search": search, "$top": str(top)}
    if select:
        params["$select"] = select
    url = f"{base}{table}"
    results: list[dict] = []
    async with httpx.AsyncClient(timeout=30) as client:
        while url:
            r = await client.get(url, auth=auth, params=params if url.startswith(base) else None)
            if r.status_code == 412:
                raise HTTPException(412, "Data Connector not activated. Install the add-in in MyGeotab Administration > System Settings > Add-Ins.")
            if r.status_code != 200:
                raise HTTPException(r.status_code, f"Data Connector error: {r.text[:500]}")
            data = r.json()
            results.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
            params = {}  # nextLink includes params
    return results


# ---------------------------------------------------------------------------
# Demo / mock data helpers
# ---------------------------------------------------------------------------

_DEMO_VEHICLE_NAMES = [
    "K1-FTW-001", "K1-FTW-002", "K1-FTW-003", "K1-FTW-004", "K1-FTW-005",
    "K1-JST-001", "K1-JST-002", "K1-JST-003",
    "K1-OKC-001", "K1-OKC-002",
    "K1-KC-001", "K1-KC-002",
]

# Fault codes that are common in commercial fleets (SAE J1939 / OBD-II)
_DEMO_FAULT_CODES = [
    ("P0401", "EGR Flow Insufficient", "medium"),
    ("P0420", "Catalyst System Efficiency Below Threshold", "high"),
    ("P0128", "Coolant Temp Below Thermostat Regulating Temp", "low"),
    ("SPN 3226", "NOx Sensor 1 - Out of Range", "high"),
    ("SPN 157", "Fuel Rail Pressure - High", "critical"),
    ("P0087", "Fuel Rail/System Pressure - Too Low", "critical"),
    ("SPN 110", "Engine Coolant Temperature - Warning", "medium"),
    ("P0299", "Turbocharger/Supercharger Underboost Condition", "high"),
    ("SPN 4334", "Aftertreatment 1 DEF Level Low", "medium"),
    ("P0471", "Exhaust Pressure Sensor Range/Performance", "low"),
]


def _demo_vehicle_kpis(days: int) -> dict:
    """Return seeded mock vehicle KPI data for demo mode."""
    rng = random.Random(42)
    scale = days / 14  # normalise to 14-day baseline
    vehicles = []
    for name in _DEMO_VEHICLE_NAMES:
        base_dist = rng.uniform(180, 580)
        distance_km = round(base_dist * scale, 1)
        avg_speed_kmh = rng.uniform(38, 62)
        drive_hours = round(distance_km / avg_speed_kmh, 1)
        idle_ratio = rng.uniform(0.10, 0.40)
        idle_hours = round(drive_hours * idle_ratio, 1)
        trips = max(1, int(drive_hours / rng.uniform(0.5, 1.8)))
        fuel_l = round(distance_km * rng.uniform(0.12, 0.18), 1)
        vehicles.append({
            "vehicle_name": name,
            "distance_km": distance_km,
            "drive_hours": drive_hours,
            "idle_hours": idle_hours,
            "trips": trips,
            "fuel_litres": fuel_l,
        })

    vehicles.sort(key=lambda v: v["distance_km"], reverse=True)
    total_dist = sum(v["distance_km"] for v in vehicles)
    total_drive = sum(v["drive_hours"] for v in vehicles)
    total_idle = sum(v["idle_hours"] for v in vehicles)
    util_pct = round(total_drive / (total_drive + total_idle) * 100, 1) if (total_drive + total_idle) > 0 else 0

    return {
        "vehicles": vehicles,
        "summary": {
            "total_vehicles": len(vehicles),
            "total_distance_km": round(total_dist, 1),
            "total_drive_hours": round(total_drive, 1),
            "total_idle_hours": round(total_idle, 1),
            "utilization_pct": util_pct,
        },
        "period_days": days,
        "demo": True,
    }


def _demo_safety_scores(days: int) -> dict:
    """Return seeded mock safety score data for demo mode."""
    rng = random.Random(42)
    vehicle_scores = []
    for name in _DEMO_VEHICLE_NAMES:
        score = round(rng.uniform(68, 98), 1)
        vehicle_scores.append({
            "VehicleName": name,
            "SafetyScore": score,
            "Trend": rng.choice(["improving", "stable", "declining"]),
            "SpeedingEvents": rng.randint(0, 6),
            "HarshBrakingEvents": rng.randint(0, 4),
            "HarshAccelerationEvents": rng.randint(0, 5),
            "HarshCorneringEvents": rng.randint(0, 3),
        })

    fleet_avg = round(sum(v["SafetyScore"] for v in vehicle_scores) / len(vehicle_scores), 1)
    fleet_daily = [
        {"Date": (datetime.now(timezone.utc) - timedelta(days=d)).strftime("%Y-%m-%d"),
         "FleetSafetyScore": round(fleet_avg + rng.uniform(-3, 3), 1)}
        for d in range(min(days, 14), 0, -1)
    ]

    return {
        "fleet_daily": fleet_daily,
        "vehicle_scores": vehicle_scores,
        "fleet_avg_score": fleet_avg,
        "period_days": days,
        "demo": True,
    }


def _demo_fault_trends(days: int) -> dict:
    """Return seeded mock fault trend data for demo mode."""
    rng = random.Random(42)
    faults = []
    for vehicle in _DEMO_VEHICLE_NAMES:
        # Each vehicle gets 0-3 random fault codes
        num_faults = rng.randint(0, 3)
        chosen_faults = rng.sample(_DEMO_FAULT_CODES, min(num_faults, len(_DEMO_FAULT_CODES)))
        for code, description, severity in chosen_faults:
            count = rng.randint(1, 8)
            day_offset = rng.randint(0, days - 1)
            faults.append({
                "VehicleName": vehicle,
                "FaultCode": code,
                "DiagnosticName": description,
                "Severity": severity,
                "Count": count,
                "Date": (datetime.now(timezone.utc) - timedelta(days=day_offset)).strftime("%Y-%m-%d"),
            })
    # Sort by count descending so most frequent faults appear first
    faults.sort(key=lambda f: f["Count"], reverse=True)
    return {"faults": faults, "period_days": days, "demo": True}


# ---------------------------------------------------------------------------
# OData helpers
# ---------------------------------------------------------------------------

@router.get("/tables")
async def list_tables():
    """List available Data Connector tables."""
    base = await _find_server()
    auth = _basic_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(base, auth=auth)
        if r.status_code != 200:
            raise HTTPException(r.status_code, r.text[:500])
        return r.json()


@router.get("/vehicle-kpis")
async def vehicle_kpis(days: int = Query(14, ge=1, le=90)):
    """Fleet utilization KPIs per vehicle.

    Returns live Geotab OData values when the Data Connector add-in is active;
    falls back to seeded demo data otherwise so the dashboard always renders.
    """
    try:
        search = f"last_{days}_day" if days in (1, 7, 14, 30, 90) else "last_14_day"
        rows = await _odata_get("VehicleKpi_Daily", search=search)
    except HTTPException:
        return _demo_vehicle_kpis(days)

    if not rows:
        return _demo_vehicle_kpis(days)

    # Aggregate per vehicle
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
    """Aggregated safety scores from Data Connector.

    Falls back to demo data when the OData server is unreachable.
    """
    try:
        search = f"last_{days}_day" if days in (1, 7, 14, 30, 90) else "last_14_day"
        # Try fleet-level first, then vehicle-level
        fleet_rows = await _odata_get("FleetSafety_Daily", search=search)
        vehicle_rows = await _odata_get("VehicleSafety_Daily", search=search)
    except HTTPException:
        return _demo_safety_scores(days)

    if not fleet_rows and not vehicle_rows:
        return _demo_safety_scores(days)

    fleet_avg: float | None = None
    if vehicle_rows:
        scores = [r.get("SafetyScore") or r.get("Score") for r in vehicle_rows if r.get("SafetyScore") or r.get("Score")]
        if scores:
            fleet_avg = round(sum(scores) / len(scores), 1)

    return {
        "fleet_daily": fleet_rows[:30],
        "vehicle_scores": vehicle_rows[:100],
        "fleet_avg_score": fleet_avg,
        "period_days": days,
    }


@router.get("/fault-trends")
async def fault_trends(days: int = Query(14, ge=1, le=90)):
    """Fault code trends from Data Connector.

    Falls back to demo data when the OData server is unreachable.
    """
    try:
        search = f"last_{days}_day" if days in (1, 7, 14, 30, 90) else "last_14_day"
        rows = await _odata_get("FaultCode_Daily", search=search)
    except HTTPException:
        return _demo_fault_trends(days)

    if not rows:
        return _demo_fault_trends(days)

    return {"faults": rows[:200], "period_days": days}


@router.get("/trip-summary")
async def trip_summary(days: int = Query(14, ge=1, le=90)):
    """Trip summaries from Data Connector."""
    search = f"last_{days}_day" if days in (1, 7, 14, 30, 90) else "last_14_day"
    rows = await _odata_get("VehicleKpi_Daily", search=search,
                            select="VehicleName,TotalTrips,TotalDistance_Km,TotalDriveTime_Hours,TotalFuel_Litres")
    return {"trips": rows[:200], "period_days": days}
