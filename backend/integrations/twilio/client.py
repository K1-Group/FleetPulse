"""Twilio SMS client for critical FleetPulse alerts."""

from __future__ import annotations

import httpx


class TwilioSmsClient:
    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        to_number: str,
        timeout_seconds: float = 10.0,
    ):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.to_number = to_number
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.from_number and self.to_number)

    def send(self, message: str) -> bool:
        if not self.configured:
            return False
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        data = {"From": self.from_number, "To": self.to_number, "Body": message[:1500]}
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, data=data, auth=(self.account_sid, self.auth_token))
        response.raise_for_status()
        return True
