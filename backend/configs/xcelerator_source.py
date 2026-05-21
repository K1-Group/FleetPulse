"""Xcelerator analytics source selection.

FleetPulse keeps Xcelerator authoritative and reads it through one configured
analytics projection. The CEO Power BI semantic model is the default path.
"""

from __future__ import annotations

import os


CEO_POWERBI_SOURCE = "ceo_powerbi"
CONFIGURED_SOURCE = "configured"
DEFAULT_REFRESH_SECONDS = 15 * 60


def _read_string(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _read_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(int(os.getenv(name, str(default))), minimum)
    except ValueError:
        return default


def xcelerator_source_mode() -> str:
    return _read_string("FLEETPULSE_XCELERATOR_SOURCE", CONFIGURED_SOURCE).casefold()


def xcelerator_ceo_powerbi_only() -> bool:
    return xcelerator_source_mode() == CEO_POWERBI_SOURCE


def xcelerator_refresh_seconds() -> int:
    return _read_int("FLEETPULSE_XCELERATOR_REFRESH_SECONDS", DEFAULT_REFRESH_SECONDS, 60)


def xcelerator_source_label() -> str:
    if xcelerator_ceo_powerbi_only():
        return "K1 Group LLC / Xcelerator CEO Dashboard Power BI semantic model"
    return "K1 Group LLC / Xcelerator configured analytics source"
