"""Read-only Microsoft Graph drive client for SharePoint folders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
import time
from typing import Any
import base64
from urllib.parse import quote

import httpx

from configs.atob_fuel import AtoBSharePointConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SharePointDriveFile:
    id: str
    name: str
    web_url: str | None
    last_modified_at: datetime | None
    size: int | None
    e_tag: str | None
    drive_id: str | None = None

    @property
    def extension(self) -> str:
        return Path(self.name).suffix.lower()


def _parse_graph_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("invalid_graph_datetime", extra={"value": value})
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _encode_drive_path(path: str) -> str:
    parts = [part for part in path.strip("/").split("/") if part]
    return "/".join(quote(part, safe="") for part in parts)


def _share_id_from_url(url: str) -> str:
    encoded = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")
    return f"u!{encoded}"


class SharePointDriveClient:
    """Small Graph client scoped to read-only SharePoint drive file access."""

    graph_base_url = "https://graph.microsoft.com/v1.0"

    def __init__(self, config: AtoBSharePointConfig):
        self.config = config
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._site_id: str | None = None
        self._drive_id: str | None = None

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

    def _request(
        self,
        method: str,
        url: str,
        *,
        include_auth: bool = True,
        follow_redirects: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        if include_auth:
            headers["Authorization"] = f"Bearer {self._get_token()}"

        attempts = self.config.retry_count + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                with httpx.Client(
                    timeout=self.config.timeout_seconds,
                    follow_redirects=follow_redirects,
                ) as client:
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

    def resolve_site_id(self) -> str:
        if self._site_id:
            return self._site_id
        if self.config.site_id:
            self._site_id = self.config.site_id
            return self._site_id

        hostname = quote(self.config.site_hostname, safe="")
        site_path = quote(self.config.site_path or "/", safe="/")
        url = f"{self.graph_base_url}/sites/{hostname}:{site_path}"
        response = self._request("GET", url, params={"$select": "id,webUrl,name"})
        site_id = response.json().get("id")
        if not site_id:
            raise RuntimeError("sharepoint_site_not_found")
        self._site_id = str(site_id)
        return self._site_id

    def resolve_drive_id(self) -> str:
        if self._drive_id:
            return self._drive_id
        if self.config.drive_id:
            self._drive_id = self.config.drive_id
            return self._drive_id

        site_id = quote(self.resolve_site_id(), safe="")
        if self.config.drive_name:
            response = self._request(
                "GET",
                f"{self.graph_base_url}/sites/{site_id}/drives",
                params={"$select": "id,name", "$top": "100"},
            )
            target = self.config.drive_name.casefold()
            for drive in response.json().get("value", []):
                if str(drive.get("name", "")).casefold() == target and drive.get("id"):
                    self._drive_id = str(drive["id"])
                    return self._drive_id
            raise RuntimeError("sharepoint_drive_not_found")

        response = self._request(
            "GET",
            f"{self.graph_base_url}/sites/{site_id}/drive",
            params={"$select": "id,name"},
        )
        drive_id = response.json().get("id")
        if not drive_id:
            raise RuntimeError("sharepoint_default_drive_not_found")
        self._drive_id = str(drive_id)
        return self._drive_id

    def list_files(self) -> list[SharePointDriveFile]:
        files = self._list_source_file_url_items()
        if len(files) >= self.config.file_limit:
            return files[: self.config.file_limit]
        if not self.config.site_configured or not self.config.folder_configured:
            return files

        drive_id = quote(self.resolve_drive_id(), safe="")
        encoded_folder = _encode_drive_path(self.config.folder_path)
        if encoded_folder:
            url = f"{self.graph_base_url}/drives/{drive_id}/root:/{encoded_folder}:/children"
        else:
            url = f"{self.graph_base_url}/drives/{drive_id}/root/children"

        params: dict[str, str] | None = {
            "$top": str(min(self.config.file_limit, 200)),
            "$select": "id,name,size,lastModifiedDateTime,eTag,webUrl,file,folder",
            "$orderby": "lastModifiedDateTime desc",
        }
        while url and len(files) < self.config.file_limit:
            response = self._request("GET", url, params=params)
            payload = response.json()
            for item in payload.get("value", []):
                if len(files) >= self.config.file_limit:
                    break
                if not item.get("file"):
                    continue
                drive_file = SharePointDriveFile(
                    id=str(item.get("id") or ""),
                    name=str(item.get("name") or ""),
                    web_url=item.get("webUrl"),
                    last_modified_at=_parse_graph_datetime(item.get("lastModifiedDateTime")),
                        size=item.get("size"),
                        e_tag=item.get("eTag"),
                        drive_id=self._drive_id,
                    )
                if drive_file.extension in self.config.file_extensions:
                    files.append(drive_file)
            url = payload.get("@odata.nextLink")
            params = None
        return files

    def _list_source_file_url_items(self) -> list[SharePointDriveFile]:
        files: list[SharePointDriveFile] = []
        for source_url in self.config.source_file_urls:
            if len(files) >= self.config.file_limit:
                break
            drive_file = self._resolve_source_file_url(source_url)
            if drive_file.extension in self.config.file_extensions:
                files.append(drive_file)
        return files

    def _resolve_source_file_url(self, source_url: str) -> SharePointDriveFile:
        share_id = quote(_share_id_from_url(source_url), safe="")
        response = self._request(
            "GET",
            f"{self.graph_base_url}/shares/{share_id}/driveItem",
            params={
                "$select": "id,name,size,lastModifiedDateTime,eTag,webUrl,parentReference,file"
            },
        )
        item = response.json()
        if not item.get("file"):
            raise RuntimeError("sharepoint_source_url_not_file")
        parent = item.get("parentReference") or {}
        drive_id = parent.get("driveId")
        if not drive_id:
            raise RuntimeError("sharepoint_source_url_drive_missing")
        return SharePointDriveFile(
            id=str(item.get("id") or ""),
            name=str(item.get("name") or ""),
            web_url=item.get("webUrl") or source_url,
            last_modified_at=_parse_graph_datetime(item.get("lastModifiedDateTime")),
            size=item.get("size"),
            e_tag=item.get("eTag"),
            drive_id=str(drive_id),
        )

    def download_file_text(self, file: SharePointDriveFile) -> str:
        drive_id = quote(file.drive_id or self.resolve_drive_id(), safe="")
        item_id = quote(file.id, safe="")
        response = self._request(
            "GET",
            f"{self.graph_base_url}/drives/{drive_id}/items/{item_id}/content",
            follow_redirects=True,
        )
        content = response.content
        for encoding in ("utf-8-sig", "utf-16", "latin-1"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="replace")
