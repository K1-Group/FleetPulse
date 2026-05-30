"""Read-only Time Doctor activity feed client.

The endpoint URL is configured instead of hard-coded so FleetPulse can point at
the approved Time Doctor API/export surface without treating Time Doctor as an
internal database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class TimeDoctorActivityFeedConfig:
    url: str
    api_token: str = ""
    timeout_seconds: int = 20

    @property
    def configured(self) -> bool:
        return bool(self.url)


def fetch_time_doctor_activity_rows(config: TimeDoctorActivityFeedConfig) -> list[dict[str, Any]]:
    if not config.configured:
        raise RuntimeError("time_doctor_activity_feed_not_configured")
    headers = {"Accept": "application/json"}
    if config.api_token:
        headers["Authorization"] = f"Bearer {config.api_token}"
    with httpx.Client(timeout=config.timeout_seconds) as client:
        response = client.get(config.url, headers=headers)
        response.raise_for_status()
        payload = response.json()
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "items", "data", "activities", "worklogs", "users"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [payload]
    return []
