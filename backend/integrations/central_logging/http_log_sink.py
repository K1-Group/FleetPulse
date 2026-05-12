"""Optional HTTP sink for SharePoint or centralized log capture."""

from __future__ import annotations

from typing import Any

import httpx


class HttpLogSink:
    def __init__(self, url: str, api_key: str = "", timeout_seconds: float = 10.0):
        self.url = url
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.url)

    def emit(self, payload: dict[str, Any]) -> bool:
        if not self.configured:
            return False
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-FleetPulse-Log-Key"] = self.api_key
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(self.url, json=payload, headers=headers)
        response.raise_for_status()
        return True
