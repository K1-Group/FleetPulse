"""Authentication/session endpoints for the FleetPulse shell."""

from __future__ import annotations

from fastapi import APIRouter, Request

from services.auth_session_service import build_auth_session

router = APIRouter()


@router.get("/session")
def session(request: Request, return_to: str | None = None):
    return build_auth_session(request, return_to)
