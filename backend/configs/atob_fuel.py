"""Configuration for AtoB fuel expense imports and SharePoint folder sync."""

from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import urlparse


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int, minimum: int = 0) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, value)


def _float_env(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, value)


def _split_extensions(value: str) -> tuple[str, ...]:
    extensions = []
    for item in value.split(","):
        cleaned = item.strip().lower()
        if not cleaned:
            continue
        extensions.append(cleaned if cleaned.startswith(".") else f".{cleaned}")
    return tuple(extensions or [".csv", ".tsv", ".txt", ".json", ".jsonl"])


def _split_env_list(value: str) -> tuple[str, ...]:
    items: list[str] = []
    for line in value.replace("\n", ",").split(","):
        cleaned = line.strip()
        if cleaned:
            items.append(cleaned)
    return tuple(items)


def _site_from_url(site_url: str) -> tuple[str, str]:
    parsed = urlparse(site_url)
    if not parsed.netloc:
        return "", ""
    return parsed.netloc, parsed.path.rstrip("/") or "/"


@dataclass(frozen=True)
class AtoBSharePointConfig:
    """Environment-backed settings for the BI-connected AtoB folder."""

    enabled: bool
    graph_tenant_id: str
    graph_client_id: str
    graph_client_secret: str
    site_id: str
    site_url: str
    site_hostname: str
    site_path: str
    drive_id: str
    drive_name: str
    folder_path: str
    source_file_urls: tuple[str, ...]
    file_extensions: tuple[str, ...]
    file_limit: int
    sync_api_key: str
    timeout_seconds: float
    retry_count: int
    retry_backoff_seconds: float
    powerbi_workspace_id: str
    powerbi_folder_id: str
    powerbi_ui_subfolder_id: str
    powerbi_report_id: str
    powerbi_semantic_model_id: str

    @classmethod
    def from_env(cls) -> "AtoBSharePointConfig":
        site_url = os.getenv("FLEETPULSE_ATOB_SHAREPOINT_SITE_URL", "").strip()
        parsed_hostname, parsed_path = _site_from_url(site_url)
        return cls(
            enabled=_bool_env("FLEETPULSE_ATOB_SHAREPOINT_ENABLED"),
            graph_tenant_id=(
                os.getenv("FLEETPULSE_ATOB_GRAPH_TENANT_ID", "").strip()
                or os.getenv("FLEETPULSE_GRAPH_TENANT_ID", "").strip()
            ),
            graph_client_id=(
                os.getenv("FLEETPULSE_ATOB_GRAPH_CLIENT_ID", "").strip()
                or os.getenv("FLEETPULSE_GRAPH_CLIENT_ID", "").strip()
            ),
            graph_client_secret=(
                os.getenv("FLEETPULSE_ATOB_GRAPH_CLIENT_SECRET", "").strip()
                or os.getenv("FLEETPULSE_GRAPH_CLIENT_SECRET", "").strip()
            ),
            site_id=os.getenv("FLEETPULSE_ATOB_SHAREPOINT_SITE_ID", "").strip(),
            site_url=site_url,
            site_hostname=(
                os.getenv("FLEETPULSE_ATOB_SHAREPOINT_SITE_HOSTNAME", "").strip()
                or parsed_hostname
            ),
            site_path=(
                os.getenv("FLEETPULSE_ATOB_SHAREPOINT_SITE_PATH", "").strip()
                or parsed_path
            ),
            drive_id=os.getenv("FLEETPULSE_ATOB_SHAREPOINT_DRIVE_ID", "").strip(),
            drive_name=os.getenv("FLEETPULSE_ATOB_SHAREPOINT_DRIVE_NAME", "").strip(),
            folder_path=os.getenv("FLEETPULSE_ATOB_SHAREPOINT_FOLDER_PATH", "atob").strip("/ "),
            source_file_urls=_split_env_list(
                os.getenv("FLEETPULSE_ATOB_SHAREPOINT_SOURCE_FILE_URLS", "")
            ),
            file_extensions=_split_extensions(
                os.getenv(
                    "FLEETPULSE_ATOB_SHAREPOINT_FILE_EXTENSIONS",
                    ".csv,.tsv,.txt,.json,.jsonl",
                )
            ),
            file_limit=_int_env("FLEETPULSE_ATOB_SHAREPOINT_FILE_LIMIT", 25, minimum=1),
            sync_api_key=os.getenv("FLEETPULSE_ATOB_SHAREPOINT_INGESTION_API_KEY", "").strip(),
            timeout_seconds=_float_env("FLEETPULSE_ATOB_SHAREPOINT_TIMEOUT_SECONDS", 20.0, minimum=1.0),
            retry_count=_int_env("FLEETPULSE_ATOB_SHAREPOINT_RETRY_COUNT", 2, minimum=0),
            retry_backoff_seconds=_float_env(
                "FLEETPULSE_ATOB_SHAREPOINT_RETRY_BACKOFF_SECONDS",
                1.0,
                minimum=0.0,
            ),
            powerbi_workspace_id=os.getenv("FLEETPULSE_ATOB_POWERBI_WORKSPACE_ID", "").strip(),
            powerbi_folder_id=os.getenv("FLEETPULSE_ATOB_POWERBI_FOLDER_ID", "").strip(),
            powerbi_ui_subfolder_id=os.getenv("FLEETPULSE_ATOB_POWERBI_UI_SUBFOLDER_ID", "").strip(),
            powerbi_report_id=os.getenv("FLEETPULSE_ATOB_POWERBI_REPORT_ID", "").strip(),
            powerbi_semantic_model_id=os.getenv(
                "FLEETPULSE_ATOB_POWERBI_SEMANTIC_MODEL_ID",
                "",
            ).strip(),
        )

    @property
    def graph_configured(self) -> bool:
        return bool(self.graph_tenant_id and self.graph_client_id and self.graph_client_secret)

    @property
    def site_configured(self) -> bool:
        return bool(self.site_id or (self.site_hostname and self.site_path))

    @property
    def folder_configured(self) -> bool:
        return bool(self.folder_path)

    @property
    def source_file_configured(self) -> bool:
        return bool(self.source_file_urls)

    @property
    def sync_ready(self) -> bool:
        source_configured = (
            (self.site_configured and self.folder_configured)
            or self.source_file_configured
        )
        return self.enabled and self.graph_configured and source_configured

    @property
    def api_key_required(self) -> bool:
        return bool(self.sync_api_key)

    def missing_sync_config(self) -> list[str]:
        missing: list[str] = []
        if not self.enabled:
            missing.append("FLEETPULSE_ATOB_SHAREPOINT_ENABLED")
        if not self.graph_tenant_id:
            missing.append("FLEETPULSE_GRAPH_TENANT_ID")
        if not self.graph_client_id:
            missing.append("FLEETPULSE_GRAPH_CLIENT_ID")
        if not self.graph_client_secret:
            missing.append("FLEETPULSE_GRAPH_CLIENT_SECRET")
        if not self.source_file_configured and not self.site_configured:
            missing.append(
                "FLEETPULSE_ATOB_SHAREPOINT_SITE_URL or "
                "FLEETPULSE_ATOB_SHAREPOINT_SITE_ID or "
                "FLEETPULSE_ATOB_SHAREPOINT_SOURCE_FILE_URLS"
            )
        if not self.source_file_configured and not self.folder_path:
            missing.append("FLEETPULSE_ATOB_SHAREPOINT_FOLDER_PATH")
        return missing
