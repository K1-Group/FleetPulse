"""Historical pickup/delivery address benchmark API."""

from __future__ import annotations

from fastapi import APIRouter, Query

from services.address_benchmark_service import get_address_benchmark_dataset


router = APIRouter()


@router.get("")
def address_benchmarks(
    pickup: str | None = Query(default=None, description="Optional pickup address/city filter."),
    delivery: str | None = Query(default=None, description="Optional delivery address/city filter."),
    days: int | None = Query(default=None, ge=1, le=730),
) -> dict:
    return get_address_benchmark_dataset(pickup=pickup, delivery=delivery, days=days)
