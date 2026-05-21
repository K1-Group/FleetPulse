"""HTTP cache policy for FleetPulse dashboard API surfaces."""

from __future__ import annotations

import os


DEFAULT_KPI_CACHE_CONTROL = "public, max-age=60, stale-while-revalidate=300"
CACHEABLE_API_PREFIXES = ("/api/data-connector/", "/api/fuel/")


def api_cache_control_header(
    method: str,
    path: str,
    status_code: int,
) -> str | None:
    """Return the browser cache policy for safe KPI GET responses."""

    if method.upper() != "GET" or status_code != 200:
        return None
    if not any(path.startswith(prefix) for prefix in CACHEABLE_API_PREFIXES):
        return None
    configured = os.getenv("FLEETPULSE_KPI_CACHE_CONTROL", "").strip()
    return configured or DEFAULT_KPI_CACHE_CONTROL
