"""Configuration for department call-analysis imports and SharePoint sync."""

from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import parse_qs, unquote, urlparse


DEFAULT_SITE_URL = "https://netorgft3187866.sharepoint.com/sites/K1SOPsandProcedures"
DEFAULT_FOLDER_PATH = "Grasshopper/Call Analysis Reports/HR"
DEFAULT_STATE_PATH = "/home/data/fleetpulse_hr_call_analysis.json"
DEFAULT_DEPARTMENTS = ("Operations", "HR", "Maintenance")


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, value)


def _int_env(name: str, default: int, minimum: int = 0) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, value)


def _split_env_list(value: str) -> tuple[str, ...]:
    items: list[str] = []
    for part in value.replace("\n", ",").split(","):
        cleaned = part.strip()
        if cleaned:
            items.append(cleaned)
    return tuple(items)


def _split_department_list(value: str) -> tuple[str, ...]:
    departments: list[str] = []
    for part in value.replace("\n", ",").split(","):
        cleaned = part.strip()
        if cleaned and cleaned not in departments:
            departments.append(cleaned)
    return tuple(departments or DEFAULT_DEPARTMENTS)


def _split_department_folder_map(value: str) -> dict[str, str]:
    """Parse Department=SharePoint/folder/path pairs from JSON or env text."""

    cleaned = value.strip()
    if not cleaned:
        return {}
    try:
        import json

        payload = json.loads(cleaned)
        if isinstance(payload, dict):
            return {
                str(department).strip(): str(folder).strip("/ ")
                for department, folder in payload.items()
                if str(department).strip() and str(folder).strip()
            }
    except Exception:
        pass

    folder_map: dict[str, str] = {}
    for part in cleaned.replace("\n", ";").split(";"):
        if not part.strip() or "=" not in part:
            continue
        department, folder = part.split("=", 1)
        department = department.strip()
        folder = folder.strip("/ ")
        if department and folder:
            folder_map[department] = folder
    return folder_map


def _split_extensions(value: str) -> tuple[str, ...]:
    extensions: list[str] = []
    for part in value.split(","):
        cleaned = part.strip().lower()
        if cleaned:
            extensions.append(cleaned if cleaned.startswith(".") else f".{cleaned}")
    return tuple(extensions or [".txt", ".csv"])


def _site_from_url(site_url: str) -> tuple[str, str]:
    parsed = urlparse(site_url)
    if not parsed.netloc:
        return "", ""
    return parsed.netloc, parsed.path.rstrip("/") or "/"


def _folder_from_sharepoint_url(folder_url: str) -> str:
    parsed = urlparse(folder_url)
    params = parse_qs(parsed.query)
    raw_id = (params.get("id") or [""])[0]
    if not raw_id:
        return ""
    decoded = unquote(raw_id)
    marker = "/Shared Documents/"
    if marker in decoded:
        return decoded.split(marker, 1)[1].strip("/")
    return decoded.strip("/")


@dataclass(frozen=True)
class HrCallAnalysisConfig:
    """Environment-backed settings for HR call analytics."""

    state_path: str
    import_api_key: str
    hash_salt: str
    active_extensions: tuple[str, ...]
    sharepoint_enabled: bool
    sharepoint_folder_url: str
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
    sync_interval_minutes: int
    timeout_seconds: float
    retry_count: int
    retry_backoff_seconds: float
    departments: tuple[str, ...]
    department_folder_paths: dict[str, str]

    @classmethod
    def from_env(cls) -> "HrCallAnalysisConfig":
        folder_url = os.getenv("SHAREPOINT_HR_CALL_ANALYSIS_FOLDER_URL", "").strip()
        site_url = (
            os.getenv("HR_CALL_ANALYSIS_SHAREPOINT_SITE_URL", "").strip()
            or DEFAULT_SITE_URL
        )
        parsed_hostname, parsed_path = _site_from_url(site_url)
        folder_path = (
            os.getenv("HR_CALL_ANALYSIS_SHAREPOINT_FOLDER_PATH", "").strip("/ ")
            or _folder_from_sharepoint_url(folder_url)
            or DEFAULT_FOLDER_PATH
        )
        return cls(
            state_path=(
                os.getenv("DEPARTMENT_CALL_ANALYSIS_STATE_PATH", "").strip()
                or os.getenv("HR_CALL_ANALYSIS_STATE_PATH", "").strip()
                or DEFAULT_STATE_PATH
            ),
            import_api_key=os.getenv("HR_CALL_ANALYSIS_IMPORT_API_KEY", "").strip(),
            hash_salt=os.getenv("HR_CALL_HASH_SALT", "fleetpulse-hr-call").strip()
            or "fleetpulse-hr-call",
            active_extensions=tuple(
                part.strip()
                for part in os.getenv("HR_CALL_ANALYSIS_ACTIVE_EXTENSIONS", "4,702,722,725,728").split(",")
                if part.strip()
            ),
            sharepoint_enabled=_bool_env("HR_CALL_ANALYSIS_SHAREPOINT_ENABLED"),
            sharepoint_folder_url=folder_url,
            graph_tenant_id=os.getenv("FLEETPULSE_GRAPH_TENANT_ID", "").strip(),
            graph_client_id=os.getenv("FLEETPULSE_GRAPH_CLIENT_ID", "").strip(),
            graph_client_secret=os.getenv("FLEETPULSE_GRAPH_CLIENT_SECRET", "").strip(),
            site_id=os.getenv("HR_CALL_ANALYSIS_SHAREPOINT_SITE_ID", "").strip(),
            site_url=site_url,
            site_hostname=(
                os.getenv("HR_CALL_ANALYSIS_SHAREPOINT_SITE_HOSTNAME", "").strip()
                or parsed_hostname
            ),
            site_path=(
                os.getenv("HR_CALL_ANALYSIS_SHAREPOINT_SITE_PATH", "").strip()
                or parsed_path
            ),
            drive_id=os.getenv("HR_CALL_ANALYSIS_SHAREPOINT_DRIVE_ID", "").strip(),
            drive_name=os.getenv("HR_CALL_ANALYSIS_SHAREPOINT_DRIVE_NAME", "").strip(),
            folder_path=folder_path,
            source_file_urls=_split_env_list(
                os.getenv("HR_CALL_ANALYSIS_SHAREPOINT_SOURCE_FILE_URLS", "")
            ),
            file_extensions=_split_extensions(
                os.getenv("HR_CALL_ANALYSIS_SHAREPOINT_FILE_EXTENSIONS", ".txt,.csv")
            ),
            file_limit=_int_env("HR_CALL_ANALYSIS_SHAREPOINT_FILE_LIMIT", 200, minimum=1),
            sync_api_key=(
                os.getenv("HR_CALL_ANALYSIS_SHAREPOINT_SYNC_API_KEY", "").strip()
                or os.getenv("HR_CALL_ANALYSIS_IMPORT_API_KEY", "").strip()
            ),
            sync_interval_minutes=_int_env("HR_CALL_ANALYSIS_SYNC_INTERVAL_MINUTES", 15, minimum=15),
            timeout_seconds=_float_env("HR_CALL_ANALYSIS_SHAREPOINT_TIMEOUT_SECONDS", 20.0, minimum=1.0),
            retry_count=_int_env("HR_CALL_ANALYSIS_SHAREPOINT_RETRY_COUNT", 2, minimum=0),
            retry_backoff_seconds=_float_env(
                "HR_CALL_ANALYSIS_SHAREPOINT_RETRY_BACKOFF_SECONDS",
                1.0,
                minimum=0.0,
            ),
            departments=_split_department_list(
                os.getenv("DEPARTMENT_CALL_ANALYSIS_DEPARTMENTS", ",".join(DEFAULT_DEPARTMENTS))
            ),
            department_folder_paths=_split_department_folder_map(
                os.getenv("DEPARTMENT_CALL_ANALYSIS_SHAREPOINT_FOLDER_PATHS", "")
            ),
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
        return self.sharepoint_enabled and self.graph_configured and source_configured

    @property
    def api_key_required(self) -> bool:
        return bool(self.import_api_key)

    @property
    def sync_api_key_required(self) -> bool:
        return bool(self.sync_api_key)

    def missing_sync_config(self) -> list[str]:
        missing: list[str] = []
        if not self.sharepoint_enabled:
            missing.append("HR_CALL_ANALYSIS_SHAREPOINT_ENABLED")
        if not self.graph_tenant_id:
            missing.append("FLEETPULSE_GRAPH_TENANT_ID")
        if not self.graph_client_id:
            missing.append("FLEETPULSE_GRAPH_CLIENT_ID")
        if not self.graph_client_secret:
            missing.append("FLEETPULSE_GRAPH_CLIENT_SECRET")
        if not self.source_file_configured and not self.site_configured:
            missing.append("HR_CALL_ANALYSIS_SHAREPOINT_SITE_URL or HR_CALL_ANALYSIS_SHAREPOINT_SITE_ID")
        if not self.source_file_configured and not self.folder_path:
            missing.append("HR_CALL_ANALYSIS_SHAREPOINT_FOLDER_PATH")
        return missing

    def safe_status(self) -> dict[str, object]:
        return {
            "projection_mode": "read_only",
            "source_authority": "Grasshopper call logs + SharePoint HR call-analysis reports",
            "state_path_configured": bool(self.state_path),
            "departments": list(self.departments),
            "api_key_required": self.api_key_required,
            "hash_salt_configured": bool(self.hash_salt),
            "active_extensions": list(self.active_extensions),
            "sharepoint": {
                "enabled": self.sharepoint_enabled,
                "sync_ready": self.sync_ready,
                "site_configured": self.site_configured,
                "drive_configured": bool(self.drive_id or self.drive_name),
                "folder_path": self.folder_path,
                "department_folder_paths": self.department_folder_paths,
                "source_file_url_count": len(self.source_file_urls),
                "file_extensions": list(self.file_extensions),
                "file_limit": self.file_limit,
                "sync_interval_minutes": self.sync_interval_minutes,
                "api_key_required": self.sync_api_key_required,
                "missing_config": self.missing_sync_config(),
            },
        }
