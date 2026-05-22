"""FleetPulse hub configuration loader.

Hub metadata is configuration. Geotab remains authoritative for asset state,
telemetry, and current positions.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "fleet_hubs.json"
MILES_TO_METERS = 1609.344


def _resolve_config_path(raw_path: str) -> Path:
    config_path = Path(raw_path)
    if config_path.is_absolute() or config_path.exists():
        return config_path

    backend_relative = Path(__file__).resolve().parent.parent / config_path
    if backend_relative.exists():
        return backend_relative

    repo_relative = Path(__file__).resolve().parent.parent.parent / config_path
    if repo_relative.exists():
        return repo_relative

    return config_path


def _float_value(value: Any, *, field: str, hub_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Fleet hub {hub_name!r} has invalid {field}") from exc


def _load_payload() -> dict[str, Any]:
    raw_json = os.getenv("FLEETPULSE_HUBS_JSON", "").strip()
    if raw_json:
        payload = json.loads(raw_json)
        if isinstance(payload, list):
            return {"hubs": payload}
        if isinstance(payload, dict):
            return payload
        raise ValueError("FLEETPULSE_HUBS_JSON must be a JSON object or array")

    config_path = _resolve_config_path(os.getenv("FLEETPULSE_HUBS_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))
    with config_path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError("Fleet hub config must be a JSON object")
    return payload


def normalize_hub_config(payload: dict[str, Any]) -> list[dict[str, Any]]:
    default_radius = _float_value(
        payload.get("default_radius_miles", 25.0),
        field="default_radius_miles",
        hub_name="default",
    )
    raw_hubs = payload.get("hubs")
    if not isinstance(raw_hubs, list) or not raw_hubs:
        raise ValueError("Fleet hub config must include a non-empty hubs list")

    hubs: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for raw_hub in raw_hubs:
        if not isinstance(raw_hub, dict):
            raise ValueError("Fleet hub entries must be objects")
        name = str(raw_hub.get("name") or "").strip()
        if not name:
            raise ValueError("Fleet hub entries must include name")
        if name in seen_names:
            raise ValueError(f"Duplicate fleet hub name: {name}")
        seen_names.add(name)

        latitude = _float_value(
            raw_hub.get("latitude", raw_hub.get("lat")),
            field="latitude",
            hub_name=name,
        )
        longitude = _float_value(
            raw_hub.get("longitude", raw_hub.get("lon")),
            field="longitude",
            hub_name=name,
        )
        radius_miles = _float_value(
            raw_hub.get("radius_miles", default_radius),
            field="radius_miles",
            hub_name=name,
        )
        if radius_miles <= 0:
            raise ValueError(f"Fleet hub {name!r} radius_miles must be greater than 0")

        hubs.append(
            {
                "name": name,
                "address": str(raw_hub.get("address") or name).strip(),
                "lat": latitude,
                "lon": longitude,
                "radius_miles": radius_miles,
                "radius_meters": radius_miles * MILES_TO_METERS,
            }
        )

    return hubs


def get_fleet_hubs() -> list[dict[str, Any]]:
    return normalize_hub_config(_load_payload())
