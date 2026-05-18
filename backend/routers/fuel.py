"""Fuel analytics endpoints."""

import asyncio
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any

from configs.atob_fuel import AtoBSharePointConfig
from geotab_client import GeotabClient
from _cache import clear_cached_prefix, get_cached, set_cached
from services.atob_sharepoint_sync_service import (
    AtoBSharePointConfigError,
    atob_sharepoint_status,
    sync_atob_sharepoint_folder,
    validate_sharepoint_sync_api_key,
)
from services.atob_fuel_expense_service import (
    get_atob_daily_trends,
    get_atob_fuel_summary,
    get_atob_fuel_transactions,
    get_atob_vehicle_costs,
    import_atob_fuel_expenses,
)
from services.entity_margin_service import get_entity_margin_snapshot
from services.k1l_operating_kpi_service import get_k1l_operating_kpi_snapshot
from services.operating_cost_service import get_operating_cost_snapshot
from services.qbo_expense_import_service import (
    get_qbo_expense_summary,
    get_qbo_expense_transactions,
    import_qbo_expenses,
    qbo_expense_import_status,
    validate_qbo_expense_import_api_key,
)
from services.xcelerator_review_orders_import_service import (
    get_xcelerator_review_orders_summary,
    import_xcelerator_review_orders,
)

router = APIRouter()


async def _run_analytics_snapshot(coro_factory):
    """Run mixed async/blocking analytics rollups away from the request event loop."""

    return await asyncio.to_thread(lambda: asyncio.run(coro_factory()))

# Average fuel costs
AVG_FUEL_PRICE_PER_GALLON = 3.45
AVG_MPG_FLEET = 24.5


class AtoBFuelImportRequest(BaseModel):
    filename: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1)
    dry_run: bool = False


class AtoBSharePointSyncRequest(BaseModel):
    dry_run: bool = False


class XceleratorReviewOrdersImportRequest(BaseModel):
    filename: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1)
    dry_run: bool = False


class QboExpenseImportRequest(BaseModel):
    filename: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1)
    dry_run: bool = False
    period_start: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    period_end: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.post("/atob/import")
async def import_atob_report(request: AtoBFuelImportRequest):
    """Import a downloaded AtoB fuel report as read-only expense evidence."""
    result = import_atob_fuel_expenses(
        request.content,
        filename=request.filename,
        dry_run=request.dry_run,
    )
    if not request.dry_run and result.imported_count:
        clear_cached_prefix("fuel:")
    return result.as_dict()


@router.post("/xcelerator/review-orders/import")
async def import_xcelerator_review_orders_report(request: XceleratorReviewOrdersImportRequest):
    """Import a downloaded Xcelerator ReviewOrders report as read-only driver-pay evidence."""
    result = import_xcelerator_review_orders(
        request.content,
        filename=request.filename,
        dry_run=request.dry_run,
    )
    if not request.dry_run and result.imported_count:
        clear_cached_prefix("fuel:")
    return result.as_dict()


@router.get("/xcelerator/review-orders/summary")
async def xcelerator_review_orders_summary(days: int = 370):
    """Return actual imported Xcelerator ReviewOrders driver-pay summary."""
    return get_xcelerator_review_orders_summary(days=days)


@router.get("/qbo/expenses/status")
async def qbo_expenses_status():
    """Return readiness for manual QBO expense imports."""
    return qbo_expense_import_status()


@router.post("/qbo/expenses/import")
async def import_qbo_expense_report(
    request: QboExpenseImportRequest,
    x_fleetpulse_qbo_key: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
):
    """Import a downloaded QBO expense report as read-only operating-cost evidence."""
    try:
        validate_qbo_expense_import_api_key(x_fleetpulse_qbo_key or x_api_key)
        result = import_qbo_expenses(
            request.content,
            filename=request.filename,
            dry_run=request.dry_run,
            period_start=request.period_start,
            period_end=request.period_end,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not request.dry_run and result.imported_count:
        clear_cached_prefix("fuel:")
    return result.as_dict()


@router.get("/qbo/expenses/summary")
async def qbo_expenses_summary(days: int = 370):
    """Return imported QBO insurance and other expense summary."""
    return get_qbo_expense_summary(days=days)


@router.get("/qbo/expenses/transactions")
async def qbo_expense_transactions(limit: int = 100):
    """Return latest imported QBO expense records."""
    return get_qbo_expense_transactions(limit=limit)


@router.get("/atob/sharepoint/status")
async def atob_sharepoint_sync_status():
    """Return readiness for the BI-connected SharePoint AtoB folder."""
    return atob_sharepoint_status()


@router.post("/atob/sharepoint/sync")
async def sync_atob_sharepoint_report_folder(
    request: AtoBSharePointSyncRequest | None = None,
    x_fleetpulse_atob_key: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
):
    """Pull downloaded AtoB fuel reports from the configured SharePoint folder."""
    config = AtoBSharePointConfig.from_env()
    try:
        validate_sharepoint_sync_api_key(config, x_fleetpulse_atob_key or x_api_key)
        result = sync_atob_sharepoint_folder(
            config,
            dry_run=bool(request.dry_run if request else False),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AtoBSharePointConfigError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="atob_sharepoint_sync_failed") from exc

    if not result.dry_run and result.imported_count:
        clear_cached_prefix("fuel:")
    return result.as_dict()


@router.get("/atob/summary")
async def atob_summary(days: int = 30):
    """Return actual imported AtoB fuel expense summary."""
    return get_atob_fuel_summary(days=days)


@router.get("/atob/transactions")
async def atob_transactions(limit: int = 100):
    """Return latest imported AtoB fuel expense records."""
    return get_atob_fuel_transactions(limit=limit)


@router.get("/operating-cost")
async def operating_cost(
    days: int = Query(90, ge=1, le=370),
    start: str | None = Query(default=None, description="Inclusive YYYY-MM-DD start date."),
    end: str | None = Query(default=None, description="Inclusive YYYY-MM-DD end date."),
):
    """Return weekly true-cost rollups from Geotab, AtoB, Xcelerator, and QBO."""
    try:
        return await _run_analytics_snapshot(
            lambda: get_operating_cost_snapshot(days=days, start=start, end=end)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/entity-margin")
async def entity_margin(
    days: int = Query(90, ge=1, le=370),
    start: str | None = Query(default=None, description="Inclusive YYYY-MM-DD start date."),
    end: str | None = Query(default=None, description="Inclusive YYYY-MM-DD end date."),
):
    """Return K1L CPM and K1G/K1L gross-margin rollups by delivery center."""
    try:
        return await _run_analytics_snapshot(
            lambda: get_entity_margin_snapshot(days=days, start=start, end=end)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/k1l-operating-kpi")
async def k1l_operating_kpi(
    date: str | None = Query(default=None, description="Optional YYYY-MM-DD cutoff date."),
):
    """Return the lightweight K1 Logistics final CPM card snapshot."""
    return await asyncio.to_thread(get_k1l_operating_kpi_snapshot, date_value=date)


@router.get("/summary")
async def fuel_summary():
    """Get fleet fuel consumption summary."""
    cache_key = "fuel:summary"
    cached = get_cached(cache_key)
    if cached:
        return cached

    try:
        client = GeotabClient.get()
        now = datetime.now(timezone.utc)
        
        # Get trips for the past 30 days
        trips_30d = client.get_trips(from_date=now - timedelta(days=30), to_date=now)
        trips_7d = [t for t in trips_30d if _parse_date(t.get("start", "")) > now - timedelta(days=7)]
        
        # Calculate distances
        dist_30d_km = sum((t.get("distance", 0) or 0) for t in trips_30d)
        dist_7d_km = sum((t.get("distance", 0) or 0) for t in trips_7d)
        
        dist_30d_mi = dist_30d_km * 0.621371
        dist_7d_mi = dist_7d_km * 0.621371
        
        # Estimate fuel consumption
        gallons_30d = dist_30d_mi / AVG_MPG_FLEET
        gallons_7d = dist_7d_mi / AVG_MPG_FLEET
        
        cost_30d = gallons_30d * AVG_FUEL_PRICE_PER_GALLON
        cost_7d = gallons_7d * AVG_FUEL_PRICE_PER_GALLON
        
        # Get exceptions to estimate fuel waste from harsh driving
        exceptions = client.get_exception_events(from_date=now - timedelta(days=30), to_date=now)
        harsh_events = len([e for e in exceptions if _is_harsh_event(e)])
        fuel_waste_gallons = harsh_events * 0.05  # ~0.05 gal wasted per harsh event
        
        devices = client.get_devices()
        
        atob_30d = get_atob_fuel_summary(days=30)
        atob_7d = get_atob_fuel_summary(days=7)

        period_30d = _apply_atob_costs(
            {
                "total_miles": round(dist_30d_mi, 0),
                "total_gallons": round(gallons_30d, 1),
                "total_cost": round(cost_30d, 2),
                "avg_mpg": AVG_MPG_FLEET,
                "cost_per_mile": round(cost_30d / max(dist_30d_mi, 1), 3),
            },
            atob_30d,
        )
        period_7d = _apply_atob_costs(
            {
                "total_miles": round(dist_7d_mi, 0),
                "total_gallons": round(gallons_7d, 1),
                "total_cost": round(cost_7d, 2),
                "avg_mpg": AVG_MPG_FLEET,
                "cost_per_mile": round(cost_7d / max(dist_7d_mi, 1), 3),
            },
            atob_7d,
        )

        result = {
            "period_30d": period_30d,
            "period_7d": period_7d,
            "waste": {
                "harsh_events": harsh_events,
                "wasted_gallons": round(fuel_waste_gallons, 1),
                "wasted_cost": round(fuel_waste_gallons * AVG_FUEL_PRICE_PER_GALLON, 2),
            },
            "fleet_size": len(devices),
            "cost_per_vehicle_30d": round(period_30d["total_cost"] / max(len(devices), 1), 2),
            "fuel_price": AVG_FUEL_PRICE_PER_GALLON,
            "fuel_cost_source": (
                "atob_manual_import"
                if atob_30d.get("transaction_count")
                else "geotab_distance_estimate"
            ),
            "atob_import": atob_30d,
        }
        
        set_cached(cache_key, result, ttl=300)
        return result
        
    except Exception as e:
        atob_30d = get_atob_fuel_summary(days=30)
        atob_7d = get_atob_fuel_summary(days=7)
        period_30d = _apply_atob_costs(_empty_period(), atob_30d, fallback_source="unavailable")
        period_7d = _apply_atob_costs(_empty_period(), atob_7d, fallback_source="unavailable")
        return {
            "period_30d": period_30d,
            "period_7d": period_7d,
            "waste": {"harsh_events": 0, "wasted_gallons": 0, "wasted_cost": 0},
            "fleet_size": 0,
            "cost_per_vehicle_30d": 0,
            "fuel_price": 3.45,
            "fuel_cost_source": (
                "atob_manual_import"
                if atob_30d.get("transaction_count")
                else "unavailable"
            ),
            "atob_import": atob_30d,
            "live_data_available": False,
            "error": str(e),
        }


@router.get("/trends")
async def fuel_trends():
    """Get daily fuel cost trends for the past 30 days."""
    cache_key = "fuel:trends"
    cached = get_cached(cache_key)
    if cached:
        return cached

    try:
        client = GeotabClient.get()
        now = datetime.now(timezone.utc)
        
        trips = client.get_trips(from_date=now - timedelta(days=30), to_date=now)
        
        # Group trips by day
        daily: dict[str, float] = {}
        for t in trips:
            start = t.get("start", "")
            if start:
                day = str(start)[:10]
                dist_km = (t.get("distance", 0) or 0)
                daily[day] = daily.get(day, 0) + dist_km
        
        # Convert to fuel cost per day
        trend_data = []
        for day in sorted(daily.keys()):
            dist_mi = daily[day] * 0.621371
            gallons = dist_mi / AVG_MPG_FLEET
            cost = gallons * AVG_FUEL_PRICE_PER_GALLON
            trend_data.append({
                "date": day,
                "miles": round(dist_mi, 0),
                "gallons": round(gallons, 1),
                "cost": round(cost, 2),
            })
        
        trend_data = _merge_atob_daily_trends(trend_data, get_atob_daily_trends(days=30))
        
        set_cached(cache_key, trend_data, ttl=300)
        return trend_data
        
    except Exception as e:
        atob_trends = get_atob_daily_trends(days=30)
        if atob_trends:
            return atob_trends
        return []


@router.get("/efficiency")
async def fuel_efficiency_by_vehicle():
    """Get per-vehicle fuel efficiency rankings."""
    cache_key = "fuel:efficiency"
    cached = get_cached(cache_key)
    if cached:
        return cached

    try:
        client = GeotabClient.get()
        now = datetime.now(timezone.utc)
        
        devices = client.get_devices()
        trips = client.get_trips(from_date=now - timedelta(days=7), to_date=now)
        exceptions = client.get_exception_events(from_date=now - timedelta(days=7), to_date=now)
        
        # Build per-device stats
        device_names = {d.get("id", ""): d.get("name", "Unknown") for d in devices}
        device_stats: dict[str, dict] = {}
        
        for t in trips:
            dev = t.get("device", {})
            dev_id = dev.get("id", "") if isinstance(dev, dict) else ""
            if dev_id not in device_stats:
                device_stats[dev_id] = {"trips": 0, "distance_km": 0, "harsh_events": 0}
            device_stats[dev_id]["trips"] += 1
            device_stats[dev_id]["distance_km"] += (t.get("distance", 0) or 0)
        
        for ex in exceptions:
            if _is_harsh_event(ex):
                dev = ex.get("device", {})
                dev_id = dev.get("id", "") if isinstance(dev, dict) else ""
                if dev_id in device_stats:
                    device_stats[dev_id]["harsh_events"] += 1
        
        atob_vehicle_costs = get_atob_vehicle_costs(days=7)
        result = []
        for dev_id, stats in device_stats.items():
            dist_mi = stats["distance_km"] * 0.621371
            if dist_mi < 10:
                continue
            
            # Penalize MPG based on harsh events
            penalty = stats["harsh_events"] * 0.3
            est_mpg = max(AVG_MPG_FLEET - penalty, 15)
            gallons = dist_mi / est_mpg
            cost = gallons * AVG_FUEL_PRICE_PER_GALLON
            
            vehicle_name = device_names.get(dev_id, dev_id)
            atob_cost = _lookup_atob_vehicle_cost(atob_vehicle_costs, vehicle_name, dev_id)
            row = {
                "vehicle_id": dev_id,
                "vehicle_name": vehicle_name,
                "miles": round(dist_mi, 0),
                "est_mpg": round(est_mpg, 1),
                "est_gallons": round(gallons, 1),
                "est_cost": round(cost, 2),
                "harsh_events": stats["harsh_events"],
                "efficiency_grade": "A" if est_mpg >= 26 else "B" if est_mpg >= 23 else "C" if est_mpg >= 20 else "D",
            }
            if atob_cost:
                row.update(
                    {
                        "actual_cost": atob_cost["actual_cost"],
                        "actual_gallons": atob_cost["actual_gallons"],
                        "fuel_cost_source": "atob_manual_import",
                        "atob_transaction_count": atob_cost["transaction_count"],
                    }
                )
            result.append(row)
        
        result.sort(key=lambda x: x["est_mpg"], reverse=True)
        
        set_cached(cache_key, result, ttl=300)
        return result
        
    except Exception as e:
        return []


def _parse_date(date_str: str) -> datetime:
    try:
        if isinstance(date_str, datetime):
            return date_str
        return datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
    except:
        return datetime.now(timezone.utc) - timedelta(days=999)


def _is_harsh_event(ex: dict) -> bool:
    rule = ex.get("rule", {})
    name = rule.get("name", "") if isinstance(rule, dict) else str(rule)
    return any(kw in name.lower() for kw in ["harsh", "brake", "accelerat", "speed", "corner"])


def _empty_period() -> dict[str, Any]:
    return {
        "total_miles": 0,
        "total_gallons": 0,
        "total_cost": 0,
        "avg_mpg": 0,
        "cost_per_mile": 0,
    }


def _apply_atob_costs(
    period: dict[str, Any],
    atob_summary: dict[str, Any],
    *,
    fallback_source: str = "geotab_distance_estimate",
) -> dict[str, Any]:
    if not atob_summary.get("transaction_count"):
        return {**period, "fuel_cost_source": fallback_source}

    total_cost = float(atob_summary.get("total_cost") or 0)
    total_gallons = float(atob_summary.get("total_gallons") or 0)
    total_miles = float(period.get("total_miles") or 0)
    gallons_for_efficiency = total_gallons or float(period.get("total_gallons") or 0)
    return {
        **period,
        "total_cost": round(total_cost, 2),
        "total_gallons": round(gallons_for_efficiency, 1),
        "avg_mpg": round(total_miles / gallons_for_efficiency, 1)
        if gallons_for_efficiency > 0 and total_miles > 0
        else period.get("avg_mpg", 0),
        "cost_per_mile": round(total_cost / max(total_miles, 1), 3),
        "actual_fuel_cost": True,
        "fuel_cost_source": "atob_manual_import",
        "atob_transaction_count": atob_summary.get("transaction_count"),
        "atob_latest_transaction_date": atob_summary.get("latest_transaction_date"),
    }


def _merge_atob_daily_trends(
    estimated_trends: list[dict[str, Any]],
    atob_trends: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not atob_trends:
        return [
            {**item, "fuel_cost_source": "geotab_distance_estimate"}
            for item in estimated_trends
        ]

    merged = {
        str(item.get("date")): {
            **item,
            "fuel_cost_source": item.get("fuel_cost_source", "geotab_distance_estimate"),
        }
        for item in estimated_trends
        if item.get("date")
    }
    for actual in atob_trends:
        day = str(actual.get("date"))
        if not day:
            continue
        existing = merged.get(day, {})
        merged[day] = {
            **existing,
            **actual,
            "miles": existing.get("miles", actual.get("miles", 0)),
            "fuel_cost_source": "atob_manual_import",
        }
    return [merged[day] for day in sorted(merged)]


def _lookup_atob_vehicle_cost(
    atob_vehicle_costs: dict[str, dict[str, Any]],
    vehicle_name: str,
    vehicle_id: str,
) -> dict[str, Any] | None:
    return atob_vehicle_costs.get(_vehicle_key(vehicle_name)) or atob_vehicle_costs.get(
        _vehicle_key(vehicle_id)
    )


def _vehicle_key(value: str | None) -> str:
    import re

    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())
