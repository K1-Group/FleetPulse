"""Read-only FleetPulse user session projection.

Microsoft Entra and Azure App Service Authentication remain authoritative for
identity. This module only reflects the Easy Auth headers already supplied to
the app and builds local login/logout URLs for the frontend.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any
from urllib.parse import quote

from fastapi import Request

ENTRA_SOURCE_AUTHORITY = "Microsoft Entra ID via Azure App Service Authentication"
_AAD_IDPS = {"aad", "azureactivedirectory"}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _safe_return_to(return_to: str | None) -> str:
    candidate = (return_to or "/").strip() or "/"
    if not candidate.startswith("/") or candidate.startswith("//") or "://" in candidate:
        return "/"
    return candidate


def _decode_principal(encoded: str | None) -> dict[str, Any]:
    if not encoded:
        return {}
    try:
        padded = encoded + ("=" * (-len(encoded) % 4))
        decoded = base64.b64decode(padded)
        payload = json.loads(decoded.decode("utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _claim_value(principal: dict[str, Any], *claim_types: str) -> str | None:
    claims = principal.get("claims")
    if not isinstance(claims, list):
        return None
    wanted = {claim.casefold() for claim in claim_types}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_type = str(claim.get("typ") or claim.get("type") or "").casefold()
        if claim_type in wanted:
            value = str(claim.get("val") or claim.get("value") or "").strip()
            if value:
                return value
    return None


def build_auth_session(request: Request, return_to: str | None = None) -> dict[str, Any]:
    auth_required = _env_bool("FLEETPULSE_ENTRA_AUTH_REQUIRED", False)
    login_enabled = _env_bool("FLEETPULSE_ENTRA_LOGIN_ENABLED", auth_required)
    safe_return_to = _safe_return_to(return_to)
    headers = request.headers

    idp = headers.get("x-ms-client-principal-idp", "").strip().lower()
    principal_header = headers.get("x-ms-client-principal", "").strip()
    principal = _decode_principal(principal_header)
    authenticated = bool(principal_header) and idp in _AAD_IDPS

    principal_name = headers.get("x-ms-client-principal-name", "").strip()
    display_name = (
        _claim_value(principal, "name")
        or principal_name
        or _claim_value(principal, "preferred_username")
    )
    email = (
        _claim_value(principal, "preferred_username", "email")
        or principal_name
        or None
    )
    principal_id = (
        headers.get("x-ms-client-principal-id", "").strip()
        or _claim_value(
            principal,
            "http://schemas.microsoft.com/identity/claims/objectidentifier",
            "oid",
        )
        or None
    )

    user = None
    if authenticated:
        user = {
            "display_name": display_name or "Signed-in user",
            "email": email,
            "principal_id": principal_id,
        }

    login_url = None
    if login_enabled or auth_required:
        login_url = f"/.auth/login/aad?post_login_redirect_uri={quote(safe_return_to, safe='')}"

    logout_url = None
    if authenticated:
        logout_url = f"/.auth/logout?post_logout_redirect_uri={quote(safe_return_to, safe='')}"

    if auth_required:
        auth_mode = "required"
    elif login_enabled:
        auth_mode = "optional"
    else:
        auth_mode = "disabled"

    return {
        "auth_mode": auth_mode,
        "auth_required": auth_required,
        "login_enabled": login_enabled,
        "authenticated": authenticated,
        "identity_provider": idp or None,
        "user": user,
        "login_url": login_url,
        "logout_url": logout_url,
        "source_authority": ENTRA_SOURCE_AUTHORITY,
        "projection_mode": "read_only",
    }
