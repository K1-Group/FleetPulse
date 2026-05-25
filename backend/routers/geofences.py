"""Geofence management endpoints."""

import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from geotab_client import GeotabClient
from _cache import get_cached, set_cached

router = APIRouter()
logger = logging.getLogger(__name__)


class GeofenceCreate(BaseModel):
    name: str
    latitude: float
    longitude: float
    radius_meters: float = 200
    color: Optional[str] = "#3b82f6"
    alert_on_enter: bool = True
    alert_on_exit: bool = True


class GeofenceResponse(BaseModel):
    id: str
    name: str
    points: list[dict]
    color: str
    active_vehicles: int = 0


@router.get("/zones")
async def get_geofences():
    """Get all geofence zones from Geotab."""
    cache_key = "geofences:all"
    cached = get_cached(cache_key)
    if cached:
        return cached

    try:
        client = GeotabClient.get()
        zones = client.get_zones()
        
        result = []
        for z in zones:
            points = z.get("points", [])
            # Convert points to simple lat/lng
            simple_points = []
            for p in (points or []):
                if isinstance(p, dict):
                    simple_points.append({
                        "lat": p.get("y", p.get("latitude", 0)),
                        "lng": p.get("x", p.get("longitude", 0)),
                    })
            
            zone_data = {
                "id": z.get("id", ""),
                "name": z.get("name", "Unknown Zone"),
                "points": simple_points,
                "color": z.get("fillColor", {}).get("value", "#3b82f6") if isinstance(z.get("fillColor"), dict) else "#3b82f6",
                "displayed": z.get("displayed", True),
                "zone_type": str(z.get("zoneTypes", [{}])[0].get("id", "")) if z.get("zoneTypes") else "custom",
                "comment": z.get("comment", ""),
            }
            result.append(zone_data)
        
        set_cached(cache_key, result, ttl=120)
        return result
        
    except Exception as e:
        logger.warning("geofence_zones_unavailable", extra={"error": str(e)})
        return []


@router.get("/activity")
async def get_geofence_activity():
    """Get recent geofence entry/exit activity."""
    cache_key = "geofences:activity"
    cached = get_cached(cache_key)
    if cached:
        return cached

    try:
        client = GeotabClient.get()
        now = datetime.now(timezone.utc)
        from_date = now - timedelta(hours=24)
        
        # Get exception events which include zone-related events
        exceptions = client.get_exception_events(from_date=from_date, to_date=now)
        
        zone_events = []
        for ex in exceptions[:50]:
            rule = ex.get("rule", {})
            rule_name = rule.get("name", "") if isinstance(rule, dict) else ""
            
            if any(kw in rule_name.lower() for kw in ["zone", "geofence", "enter", "exit", "area"]):
                zone_events.append({
                    "id": ex.get("id", ""),
                    "vehicle": ex.get("device", {}).get("name", "Unknown") if isinstance(ex.get("device"), dict) else "Unknown",
                    "event_type": "exit" if "exit" in rule_name.lower() else "enter",
                    "zone_name": rule_name,
                    "timestamp": str(ex.get("activeFrom", now.isoformat())),
                })
        
        set_cached(cache_key, zone_events, ttl=60)
        return zone_events
        
    except Exception as e:
        logger.warning("geofence_activity_unavailable", extra={"error": str(e)})
        return []


@router.post("/create")
async def create_geofence(geofence: GeofenceCreate):
    """Create a new circular geofence zone."""
    try:
        client = GeotabClient.get()
        
        import math
        # Generate circle points (16-sided polygon)
        points = []
        for i in range(16):
            angle = 2 * math.pi * i / 16
            dlat = geofence.radius_meters / 111320
            dlng = geofence.radius_meters / (111320 * math.cos(math.radians(geofence.latitude)))
            points.append({
                "x": geofence.longitude + dlng * math.cos(angle),
                "y": geofence.latitude + dlat * math.sin(angle),
            })
        
        zone_data = {
            "name": geofence.name,
            "points": points,
            "displayed": True,
            "comment": f"Created by FleetPulse on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        }
        
        zone_id = client.add_zone(zone_data)
        
        # Invalidate cache
        set_cached("geofences:all", None, ttl=0)
        
        return {
            "id": zone_id,
            "name": geofence.name,
            "status": "created",
            "message": f"Geofence '{geofence.name}' created successfully"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Geotab geofence creation is unavailable; no fallback zone was created. {type(e).__name__}: {e}",
        ) from e
