"""Read-only Microsoft Entra seat access projection for FleetPulse.

Microsoft Entra security groups are the authority for seat membership. This
module only maps Easy Auth claims into FleetPulse dashboard access metadata; it
does not write back to Entra, Xcelerator, Geotab, SharePoint, or Power BI.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from fastapi import Request

GROUP_CLAIM_TYPES = {
    "groups",
    "group",
    "roles",
    "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups",
}

DEFAULT_PUBLIC_TABS = [
    "dashboard",
    "control-tower",
    "maintenance",
    "stability",
]

DEFAULT_SEAT_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "executive_command",
        "display_name": "Executive Command Seat",
        "tabs": [
            "dashboard",
            "control-tower",
            "finance",
            "operating-system",
            "hr-recruiting",
            "maintenance",
            "coaching",
            "replay",
            "stability",
            "reports",
            "geofences",
            "fuel",
            "compliance",
            "data-connector",
        ],
    },
    {
        "id": "revenue_manager",
        "display_name": "Revenue Manager Seat",
        "tabs": ["dashboard", "control-tower", "finance", "operating-system", "stability"],
    },
    {
        "id": "operations_manager",
        "display_name": "Operations Manager Seat",
        "tabs": [
            "dashboard",
            "control-tower",
            "operating-system",
            "replay",
            "stability",
            "reports",
        ],
    },
    {
        "id": "finance_controller",
        "display_name": "Finance Controller Seat",
        "tabs": ["dashboard", "control-tower", "finance", "operating-system", "fuel"],
    },
    {
        "id": "fleet_compliance_manager",
        "display_name": "Fleet & Compliance Manager Seat",
        "tabs": [
            "dashboard",
            "control-tower",
            "maintenance",
            "coaching",
            "replay",
            "geofences",
            "fuel",
            "compliance",
            "data-connector",
        ],
    },
    {
        "id": "people_systems_manager",
        "display_name": "People & Systems Manager Seat",
        "tabs": ["dashboard", "operating-system", "hr-recruiting", "reports"],
    },
]

PATH_TAB_PREFIXES = [
    ("/api/auth", "dashboard"),
    ("/api/dashboard", "dashboard"),
    ("/api/control-tower", "control-tower"),
    ("/api/fuel", "fuel"),
    ("/api/hr-recruiting", "hr-recruiting"),
    ("/api/hr-call-analysis", "hr-recruiting"),
    ("/api/department-call-analysis", "hr-recruiting"),
    ("/api/maintenance", "maintenance"),
    ("/api/coaching", "coaching"),
    ("/api/trips", "replay"),
    ("/api/reports", "reports"),
    ("/api/geofences", "geofences"),
    ("/api/compliance", "compliance"),
    ("/api/data-connector", "data-connector"),
    ("/api/driver-workforce", "control-tower"),
    ("/api/lane-stability", "stability"),
    ("/api/vehicles", "dashboard"),
    ("/api/safety", "dashboard"),
    ("/api/alerts", "dashboard"),
    ("/api/gamification", "dashboard"),
]


@dataclass(frozen=True)
class SeatAccessConfig:
    audit_decisions: bool
    enforce_access: bool
    public_tabs: list[str]
    seat_definitions: list[dict[str, Any]]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _json_env(name: str) -> dict[str, Any]:
    value = os.getenv(name, "").strip()
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _claim_values(principal: dict[str, Any], claim_types: set[str]) -> list[str]:
    claims = principal.get("claims")
    if not isinstance(claims, list):
        return []
    wanted = {claim_type.casefold() for claim_type in claim_types}
    values: list[str] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_type = str(claim.get("typ") or claim.get("type") or "").casefold()
        if claim_type not in wanted:
            continue
        value = str(claim.get("val") or claim.get("value") or "").strip()
        if value:
            values.append(value)
    return values


def _normalize_definition(definition: dict[str, Any], configured: dict[str, Any]) -> dict[str, Any]:
    tabs = configured.get("tabs") or definition.get("tabs") or []
    if isinstance(tabs, str):
        tabs = [item.strip() for item in tabs.split(",") if item.strip()]
    group_id = str(configured.get("groupId") or configured.get("group_id") or "").strip()
    return {
        "display_name": str(
            configured.get("displayName")
            or configured.get("display_name")
            or definition["display_name"]
        ).strip(),
        "group_id": group_id.lower(),
        "id": definition["id"],
        "tabs": [str(tab).strip() for tab in tabs if str(tab).strip()],
    }


def get_seat_access_config() -> SeatAccessConfig:
    configured_groups = _json_env("FLEETPULSE_ENTRA_SEAT_GROUPS_JSON")
    seat_definitions = [
        _normalize_definition(definition, configured_groups.get(definition["id"], {}))
        for definition in DEFAULT_SEAT_DEFINITIONS
    ]
    return SeatAccessConfig(
        audit_decisions=_env_bool("FLEETPULSE_ENTRA_AUDIT_DECISIONS", True),
        enforce_access=_env_bool("FLEETPULSE_ENTRA_SEAT_ACCESS_ENFORCED", False),
        public_tabs=_csv_env("FLEETPULSE_ENTRA_PUBLIC_TABS", DEFAULT_PUBLIC_TABS),
        seat_definitions=seat_definitions,
    )


def build_seat_access(principal: dict[str, Any], authenticated: bool) -> dict[str, Any]:
    config = get_seat_access_config()
    group_ids = {value.casefold() for value in _claim_values(principal, GROUP_CLAIM_TYPES)}
    seats = [
        {
            "display_name": definition["display_name"],
            "id": definition["id"],
            "tabs": definition["tabs"],
        }
        for definition in config.seat_definitions
        if definition["group_id"] and definition["group_id"] in group_ids
    ]
    allowed_tabs = sorted({*config.public_tabs, *(tab for seat in seats for tab in seat["tabs"])})
    config_ready = any(definition["group_id"] for definition in config.seat_definitions)
    needs_seat = config.enforce_access and authenticated
    authorized = not needs_seat or bool(seats)

    return {
        "allowed_tabs": allowed_tabs,
        "authorization_mode": "enforced" if config.enforce_access else "optional",
        "authorized": authorized,
        "config_ready": config_ready,
        "denied_reason": None if authorized else "entra_seat_required",
        "primary_seat": seats[0] if seats else None,
        "projection_mode": "read_only",
        "public_tabs": config.public_tabs,
        "seats": seats,
        "source_authority": "Microsoft Entra security groups",
        "write_back_allowed": False,
    }


def tab_for_path(path: str) -> str | None:
    for prefix, tab in PATH_TAB_PREFIXES:
        if path == prefix or path.startswith(f"{prefix}/"):
            return tab
    return None


def authorize_request_path(request: Request, principal: dict[str, Any], authenticated: bool) -> dict[str, Any]:
    access = build_seat_access(principal, authenticated)
    tab = tab_for_path(request.url.path)
    allowed = (
        not get_seat_access_config().enforce_access
        or tab is None
        or tab in access["allowed_tabs"]
    )
    return {
        "access": access,
        "allowed": allowed,
        "denied_reason": None if allowed else "tab_not_allowed_for_entra_seat",
        "tab": tab,
    }
