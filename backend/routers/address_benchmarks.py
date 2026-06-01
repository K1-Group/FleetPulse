"""Historical pickup/delivery address benchmark API."""

from __future__ import annotations

from fastapi import APIRouter, Query

from services.address_benchmark_service import get_address_benchmark_dataset


router = APIRouter()


def _optional_filter(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


@router.get("")
def address_benchmarks(
    pickup: str | None = Query(default=None, description="Optional pickup address/city filter."),
    delivery: str | None = Query(default=None, description="Optional delivery address/city filter."),
    route: str | None = Query(default=None, description="Optional Xcelerator route/lane filter."),
    days: int | None = Query(default=None, ge=1, le=730),
) -> dict:
    return get_address_benchmark_dataset(
        pickup=_optional_filter(pickup),
        delivery=_optional_filter(delivery),
        route=_optional_filter(route),
        days=days,
    )
