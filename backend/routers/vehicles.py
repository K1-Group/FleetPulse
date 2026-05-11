"""Vehicle detail endpoints."""

from fastapi import APIRouter

from models import Vehicle
from services.fleet_service import get_vehicles

router = APIRouter()


@router.get("/", response_model=list[Vehicle])
def list_vehicles():
    return get_vehicles()


@router.get("/{vehicle_id}", response_model=Vehicle)
def get_vehicle(vehicle_id: str):
    vehicles = get_vehicles()
    for v in vehicles:
        if v.id == vehicle_id:
            return v
    return Vehicle(id=vehicle_id, name="Not Found")
