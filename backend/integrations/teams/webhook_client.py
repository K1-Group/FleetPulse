"""Teams webhook client for critical FleetPulse alerts."""

from __future__ import annotations

import httpx


class TeamsWebhookClient:
    def __init__(self, webhook_url: str, timeout_seconds: float = 10.0):
        self.webhook_url = webhook_url
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.webhook_url)

    def send(self, title: str, text: str) -> bool:
        if not self.configured:
            return False
        payload = {"title": title, "text": text}
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(self.webhook_url, json=payload)
        response.raise_for_status()
        return True
