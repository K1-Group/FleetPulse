"""Tests for read-only FleetPulse auth session projection."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from routers import auth  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/auth")
    return TestClient(app)


def _principal(claims: list[dict[str, str]]) -> str:
    payload = json.dumps({"claims": claims}).encode("utf-8")
    return base64.b64encode(payload).decode("ascii").rstrip("=")


def test_session_returns_optional_login_without_identity(monkeypatch):
    monkeypatch.delenv("FLEETPULSE_ENTRA_AUTH_REQUIRED", raising=False)
    monkeypatch.setenv("FLEETPULSE_ENTRA_LOGIN_ENABLED", "true")

    response = _client().get("/api/auth/session?return_to=%2F%23dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["auth_mode"] == "optional"
    assert payload["auth_required"] is False
    assert payload["login_enabled"] is True
    assert payload["authenticated"] is False
    assert payload["user"] is None
    assert payload["login_url"] == "/.auth/login/aad?post_login_redirect_uri=%2F%23dashboard"
    assert payload["projection_mode"] == "read_only"


def test_session_decodes_easy_auth_user(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_ENTRA_LOGIN_ENABLED", "true")
    headers = {
        "x-ms-client-principal": _principal(
            [
                {"typ": "name", "val": "Rami Tashtoosh"},
                {"typ": "preferred_username", "val": "rami@k1group.net"},
            ]
        ),
        "x-ms-client-principal-idp": "aad",
        "x-ms-client-principal-id": "principal-123",
        "x-ms-client-principal-name": "fallback@k1group.net",
    }

    response = _client().get("/api/auth/session", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is True
    assert payload["identity_provider"] == "aad"
    assert payload["user"] == {
        "display_name": "Rami Tashtoosh",
        "email": "rami@k1group.net",
        "principal_id": "principal-123",
    }
    assert payload["logout_url"] == "/.auth/logout?post_logout_redirect_uri=%2F"


def test_session_rejects_external_return_url(monkeypatch):
    monkeypatch.setenv("FLEETPULSE_ENTRA_LOGIN_ENABLED", "true")

    response = _client().get("/api/auth/session?return_to=https%3A%2F%2Fevil.example")

    assert response.status_code == 200
    assert response.json()["login_url"] == "/.auth/login/aad?post_login_redirect_uri=%2F"
