"""Read-only Power BI connector endpoints for FleetPulse."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from services.entity_margin_service import get_entity_margin_snapshot
from services.fleet_service import get_fleet_overview, get_location_stats, get_vehicles
from services.lane_stability_service import get_lane_stability_snapshot
from services.operating_cost_service import get_operating_cost_snapshot
from services.safety_service import get_safety_scores

router = APIRouter()
POWERBI_DIR = Path(__file__).resolve().parents[2] / "powerbi"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    raise TypeError(f"Unsupported Power BI row type: {type(value).__name__}")


def _with_export_meta(
    row: dict[str, Any],
    connection_name: str,
    *,
    source_system: str = "FleetPulse",
    source_authority: str = "Geotab",
) -> dict[str, Any]:
    return {
        **row,
        "connection_name": connection_name,
        "exported_at": _now_iso(),
        "source_system": source_system,
        "source_authority": source_authority,
        "projection_mode": "read_only",
    }


def _with_lane_stability_meta(row: dict[str, Any], connection_name: str) -> dict[str, Any]:
    return _with_export_meta(
        row,
        connection_name,
        source_system="Xcelerator",
        source_authority="K1 Group LLC / Xcelerator",
    )


def _with_operating_cost_meta(row: dict[str, Any], connection_name: str) -> dict[str, Any]:
    return _with_export_meta(
        row,
        connection_name,
        source_system="FleetPulse Cost Analytics",
        source_authority="Geotab + AtoB + Xcelerator + QuickBooks",
    )


def _with_entity_margin_meta(row: dict[str, Any], connection_name: str) -> dict[str, Any]:
    return _with_export_meta(
        row,
        connection_name,
        source_system="FleetPulse Entity Margin",
        source_authority="Geotab + AtoB + QBO + Xcelerator",
    )


@router.get("/overview")
async def powerbi_overview() -> list[dict[str, Any]]:
    """Power BI connection 1: one-row fleet overview KPI table."""
    return [_with_export_meta(_dump(get_fleet_overview()), "fleetpulse_overview")]


@router.get("/locations")
async def powerbi_locations() -> list[dict[str, Any]]:
    """Power BI connection 2: location-level fleet table."""
    return [
        _with_export_meta(_dump(location), "fleetpulse_locations")
        for location in get_location_stats()
    ]


@router.get("/vehicles")
async def powerbi_vehicles() -> list[dict[str, Any]]:
    """Power BI connection 3: vehicle status and position table."""
    rows: list[dict[str, Any]] = []
    for vehicle in get_vehicles():
        row = _dump(vehicle)
        position = row.pop("position", None) or {}
        row["latitude"] = position.get("latitude")
        row["longitude"] = position.get("longitude")
        row["bearing"] = position.get("bearing")
        row["speed"] = position.get("speed")
        rows.append(_with_export_meta(row, "fleetpulse_vehicles"))
    return rows


@router.get("/safety-scores")
async def powerbi_safety_scores(days: int = Query(7, ge=1, le=90)) -> list[dict[str, Any]]:
    """Power BI connection 4: vehicle safety score table."""
    rows: list[dict[str, Any]] = []
    for score in get_safety_scores(days=days):
        row = _dump(score)
        breakdown = row.pop("breakdown", {}) or {}
        row["speeding_events"] = breakdown.get("speeding", 0)
        row["harsh_braking_events"] = breakdown.get("harsh_braking", 0)
        row["harsh_acceleration_events"] = breakdown.get("harsh_acceleration", 0)
        row["harsh_cornering_events"] = breakdown.get("harsh_cornering", 0)
        row["period_days"] = days
        rows.append(_with_export_meta(row, "fleetpulse_safety_scores"))
    return rows


@router.get("/fleetpulse-snapshot")
async def powerbi_fleetpulse_snapshot(days: int = Query(7, ge=1, le=90)) -> dict[str, Any]:
    """Power BI connection 5: combined FleetPulse snapshot for one-source imports."""
    overview = await powerbi_overview()
    locations = await powerbi_locations()
    vehicles = await powerbi_vehicles()
    safety_scores = await powerbi_safety_scores(days=days)

    return {
        "connection_name": "fleetpulse_snapshot",
        "exported_at": _now_iso(),
        "source_system": "FleetPulse",
        "source_authority": "Geotab",
        "projection_mode": "read_only",
        "period_days": days,
        "tables": {
            "overview": overview,
            "locations": locations,
            "vehicles": vehicles,
            "safety_scores": safety_scores,
        },
        "row_counts": {
            "overview": len(overview),
            "locations": len(locations),
            "vehicles": len(vehicles),
            "safety_scores": len(safety_scores),
        },
    }


@router.get("/lane-stability/company")
async def powerbi_lane_stability_company(days: int = Query(7, ge=1, le=90)) -> list[dict[str, Any]]:
    """Power BI lane stability table: company KPIs from Xcelerator orders."""
    snapshot = get_lane_stability_snapshot(days=days)
    return [_with_lane_stability_meta(snapshot["company_kpis"], "lane_stability_company")]


@router.get("/lane-stability/by-service")
async def powerbi_lane_stability_by_service(days: int = Query(7, ge=1, le=90)) -> list[dict[str, Any]]:
    """Power BI lane stability table: service-level rollup."""
    snapshot = get_lane_stability_snapshot(days=days)
    period = {
        "period_start": snapshot["period_start"],
        "period_end": snapshot["period_end"],
        "feed_status": snapshot["feed_status"],
    }
    return [
        _with_lane_stability_meta({**period, **row}, "lane_stability_by_service")
        for row in snapshot["by_service"]
    ]


@router.get("/lane-stability/lanes")
async def powerbi_lane_stability_lanes(days: int = Query(7, ge=1, le=90)) -> list[dict[str, Any]]:
    """Power BI lane stability table: lane-level driver stability."""
    snapshot = get_lane_stability_snapshot(days=days)
    period = {
        "period_start": snapshot["period_start"],
        "period_end": snapshot["period_end"],
        "feed_status": snapshot["feed_status"],
    }
    return [
        _with_lane_stability_meta({**period, **row}, "lane_stability_lanes")
        for row in snapshot["lanes"]
    ]


@router.get("/lane-stability/routes")
async def powerbi_lane_stability_routes(days: int = Query(7, ge=1, le=90)) -> list[dict[str, Any]]:
    """Power BI lane stability table: route-slot breakdown within each lane."""
    snapshot = get_lane_stability_snapshot(days=days)
    period = {
        "period_start": snapshot["period_start"],
        "period_end": snapshot["period_end"],
        "feed_status": snapshot["feed_status"],
    }
    return [
        _with_lane_stability_meta({**period, **row}, "lane_stability_routes")
        for row in snapshot["routes"]
    ]


@router.get("/lane-stability/daily")
async def powerbi_lane_stability_daily(days: int = Query(7, ge=1, le=90)) -> list[dict[str, Any]]:
    """Power BI lane stability table: daily operational review trend."""
    snapshot = get_lane_stability_snapshot(days=days)
    period = {
        "period_start": snapshot["period_start"],
        "period_end": snapshot["period_end"],
        "feed_status": snapshot["feed_status"],
    }
    return [
        _with_lane_stability_meta({**period, **row}, "lane_stability_daily")
        for row in snapshot["daily"]
    ]


@router.get("/lane-stability/trend")
async def powerbi_lane_stability_trend(days: int = Query(7, ge=1, le=90)) -> list[dict[str, Any]]:
    """Power BI lane stability table: better/worse lane deltas vs baseline."""
    snapshot = get_lane_stability_snapshot(days=days)
    return [
        _with_lane_stability_meta(row, "lane_stability_trend")
        for row in snapshot["trend"]
    ]


@router.get("/lane-stability-snapshot")
async def powerbi_lane_stability_snapshot(days: int = Query(7, ge=1, le=90)) -> dict[str, Any]:
    """Power BI lane stability snapshot for one-source imports."""
    snapshot = get_lane_stability_snapshot(days=days)
    return {
        "connection_name": "lane_stability_snapshot",
        "exported_at": _now_iso(),
        "source_system": "Xcelerator",
        "source_authority": "K1 Group LLC / Xcelerator",
        "projection_mode": "read_only",
        **snapshot,
    }


@router.get("/operating-cost/summary")
async def powerbi_operating_cost_summary(
    days: int = Query(90, ge=1, le=370),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """Power BI operating cost table: one-row cost-per-mile/hour summary."""
    snapshot = await get_operating_cost_snapshot(days=days, start=start, end=end)
    row = {
        "period_start": snapshot["period_start"],
        "period_end": snapshot["period_end"],
        "generated_at": snapshot["generated_at"],
        "complete_cost_available": snapshot["complete_cost_available"],
        "unresolved_sources": ",".join(snapshot["unresolved_sources"]),
        **snapshot["summary"],
    }
    return [_with_operating_cost_meta(row, "operating_cost_summary")]


@router.get("/operating-cost/weekly")
async def powerbi_operating_cost_weekly(
    days: int = Query(90, ge=1, le=370),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """Power BI operating cost table: weekly cost-per-mile/hour trend."""
    snapshot = await get_operating_cost_snapshot(days=days, start=start, end=end)
    period = {
        "period_start": snapshot["period_start"],
        "period_end": snapshot["period_end"],
        "complete_cost_available": snapshot["complete_cost_available"],
        "unresolved_sources": ",".join(snapshot["unresolved_sources"]),
    }
    return [
        _with_operating_cost_meta({**period, **row}, "operating_cost_weekly")
        for row in snapshot["weekly"]
    ]


@router.get("/entity-margin/summary")
async def powerbi_entity_margin_summary(
    days: int = Query(90, ge=1, le=370),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """Power BI entity margin table: K1L CPM and K1G/K1L margin summary."""
    snapshot = await get_entity_margin_snapshot(days=days, start=start, end=end)
    row = {
        "period_start": snapshot["period_start"],
        "period_end": snapshot["period_end"],
        "generated_at": snapshot["generated_at"],
        "k1l_margin_target_pct": snapshot["k1l_margin_target_pct"],
        "k1g_margin_target_pct": snapshot["k1g_margin_target_pct"],
        "complete_k1l_cpm_available": snapshot["complete_k1l_cpm_available"],
        "complete_k1l_true_cpm_available": snapshot["complete_k1l_true_cpm_available"],
        "unresolved_sources": ",".join(snapshot["unresolved_sources"]),
        "true_cpm_unresolved_sources": ",".join(snapshot["true_cpm_unresolved_sources"]),
        "xcelerator_source_type": snapshot["xcelerator_source_type"],
        **snapshot["summary"],
    }
    return [_with_entity_margin_meta(row, "entity_margin_summary")]


@router.get("/entity-margin/weekly")
async def powerbi_entity_margin_weekly(
    days: int = Query(90, ge=1, le=370),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """Power BI entity margin table: weekly K1L CPM and K1G/K1L margin trend."""
    snapshot = await get_entity_margin_snapshot(days=days, start=start, end=end)
    period = {
        "period_start": snapshot["period_start"],
        "period_end": snapshot["period_end"],
        "k1l_margin_target_pct": snapshot["k1l_margin_target_pct"],
        "k1g_margin_target_pct": snapshot["k1g_margin_target_pct"],
        "complete_k1l_cpm_available": snapshot["complete_k1l_cpm_available"],
        "complete_k1l_true_cpm_available": snapshot["complete_k1l_true_cpm_available"],
        "unresolved_sources": ",".join(snapshot["unresolved_sources"]),
        "true_cpm_unresolved_sources": ",".join(snapshot["true_cpm_unresolved_sources"]),
        "xcelerator_source_type": snapshot["xcelerator_source_type"],
    }
    return [
        _with_entity_margin_meta({**period, **row}, "entity_margin_weekly")
        for row in snapshot["weekly"]
    ]


@router.get("/dashboard-preview", response_class=HTMLResponse)
async def powerbi_dashboard_preview() -> HTMLResponse:
    """Serve the read-only FleetPulse Power BI dashboard preview."""
    dashboard_path = POWERBI_DIR / "fleetpulse_dashboard.html"
    return HTMLResponse(dashboard_path.read_text(encoding="utf-8"))
