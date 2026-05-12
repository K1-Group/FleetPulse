"""Read-only Microsoft Graph mailbox client for XTRA Lease emails."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import time
from typing import Any
from urllib.parse import quote

import httpx

from configs.xtra_lease import XtraLeaseIngestionConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutlookMessage:
    id: str
    subject: str
    received_at: datetime
    body_preview: str
    from_address: str | None = None
    internet_message_id: str | None = None
    web_link: str | None = None


def _parse_graph_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("invalid_graph_datetime", extra={"value": value})
        return datetime.now(timezone.utc)
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _from_address(raw_from: dict[str, Any] | None) -> str | None:
    if not raw_from:
        return None
    email = raw_from.get("emailAddress") or {}
    return email.get("address") or email.get("name")


class GraphMailClient:
    """Small Graph client scoped to mailbox folder reads."""

    graph_base_url = "https://graph.microsoft.com/v1.0"

    def __init__(self, config: XtraLeaseIngestionConfig):
        self.config = config
        self._token: str | None = None
        self._token_expires_at = 0.0

    def _token_url(self) -> str:
        tenant = quote(self.config.graph_tenant_id, safe="")
        return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        data = {
            "client_id": self.config.graph_client_id,
            "client_secret": self.config.graph_client_secret,
            "grant_type": "client_credentials",
            "scope": "https://graph.microsoft.com/.default",
        }
        response = self._request("POST", self._token_url(), data=data, include_auth=False)
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("graph_token_missing")
        self._token = str(token)
        self._token_expires_at = time.time() + int(payload.get("expires_in", 3600))
        return self._token

    def _request(self, method: str, url: str, include_auth: bool = True, **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        if include_auth:
            headers["Authorization"] = f"Bearer {self._get_token()}"

        attempts = self.config.retry_count + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                with httpx.Client(timeout=self.config.timeout_seconds) as client:
                    response = client.request(method, url, headers=headers, **kwargs)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < attempts - 1:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else self.config.retry_backoff_seconds
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                return response
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(self.config.retry_backoff_seconds)
                    continue
                raise RuntimeError(f"graph_request_failed:{type(exc).__name__}") from exc
        raise RuntimeError("graph_request_failed") from last_error

    def resolve_folder_id(self) -> str:
        mailbox = quote(self.config.mailbox, safe="")
        url = f"{self.graph_base_url}/users/{mailbox}/mailFolders"
        response = self._request(
            "GET",
            url,
            params={"$top": "100", "$select": "id,displayName"},
        )
        target = self.config.geofence_folder.casefold()
        for folder in response.json().get("value", []):
            if str(folder.get("displayName", "")).casefold() == target:
                folder_id = folder.get("id")
                if folder_id:
                    return str(folder_id)
        raise RuntimeError("xtra_geofence_folder_not_found")

    def list_messages(self) -> list[OutlookMessage]:
        mailbox = quote(self.config.mailbox, safe="")
        folder_id = quote(self.resolve_folder_id(), safe="")
        url = f"{self.graph_base_url}/users/{mailbox}/mailFolders/{folder_id}/messages"
        params = {
            "$top": str(self.config.message_limit),
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,receivedDateTime,bodyPreview,from,internetMessageId,webLink",
        }
        messages: list[OutlookMessage] = []
        while url and len(messages) < self.config.message_limit:
            response = self._request("GET", url, params=params)
            payload = response.json()
            for item in payload.get("value", []):
                if len(messages) >= self.config.message_limit:
                    break
                messages.append(
                    OutlookMessage(
                        id=str(item.get("id") or ""),
                        subject=str(item.get("subject") or ""),
                        received_at=_parse_graph_datetime(item.get("receivedDateTime")),
                        body_preview=str(item.get("bodyPreview") or ""),
                        from_address=_from_address(item.get("from")),
                        internet_message_id=item.get("internetMessageId"),
                        web_link=item.get("webLink"),
                    )
                )
            url = payload.get("@odata.nextLink")
            params = None
        return messages
