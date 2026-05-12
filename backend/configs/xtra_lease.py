"""Configuration for the XTRA Lease Outlook ingestion adapter."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


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


@dataclass(frozen=True)
class XtraLeaseIngestionConfig:
    """Environment-backed settings for read-only XTRA email ingestion."""

    enabled: bool
    mailbox: str
    geofence_folder: str
    graph_tenant_id: str
    graph_client_id: str
    graph_client_secret: str
    ingestion_api_key: str
    state_path: Path
    lookback_hours: int
    message_limit: int
    retained_event_limit: int
    timeout_seconds: float
    retry_count: int
    retry_backoff_seconds: float
    structured_log_url: str
    structured_log_api_key: str
    teams_alert_webhook_url: str
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str
    twilio_to_number: str

    @classmethod
    def from_env(cls) -> "XtraLeaseIngestionConfig":
        return cls(
            enabled=_bool_env("FLEETPULSE_XTRA_INGESTION_ENABLED"),
            mailbox=os.getenv("FLEETPULSE_XTRA_OUTLOOK_MAILBOX", "").strip(),
            geofence_folder=os.getenv("FLEETPULSE_XTRA_GEOFENCE_FOLDER", "").strip(),
            graph_tenant_id=os.getenv("FLEETPULSE_GRAPH_TENANT_ID", "").strip(),
            graph_client_id=os.getenv("FLEETPULSE_GRAPH_CLIENT_ID", "").strip(),
            graph_client_secret=os.getenv("FLEETPULSE_GRAPH_CLIENT_SECRET", "").strip(),
            ingestion_api_key=os.getenv("FLEETPULSE_XTRA_INGESTION_API_KEY", "").strip(),
            state_path=Path(
                os.getenv(
                    "FLEETPULSE_XTRA_STATE_PATH",
                    "/tmp/fleetpulse_xtra_lease_ingestion_state.json",
                )
            ),
            lookback_hours=_int_env("FLEETPULSE_XTRA_LOOKBACK_HOURS", 48, minimum=1),
            message_limit=_int_env("FLEETPULSE_XTRA_MESSAGE_LIMIT", 50, minimum=1),
            retained_event_limit=_int_env("FLEETPULSE_XTRA_RETAINED_EVENT_LIMIT", 500, minimum=1),
            timeout_seconds=_float_env("FLEETPULSE_XTRA_TIMEOUT_SECONDS", 15.0, minimum=1.0),
            retry_count=_int_env("FLEETPULSE_XTRA_RETRY_COUNT", 2, minimum=0),
            retry_backoff_seconds=_float_env("FLEETPULSE_XTRA_RETRY_BACKOFF_SECONDS", 1.0, minimum=0.0),
            structured_log_url=(
                os.getenv("FLEETPULSE_XTRA_SHAREPOINT_LOG_WEBHOOK_URL", "").strip()
                or os.getenv("FLEETPULSE_STRUCTURED_LOG_WEBHOOK_URL", "").strip()
            ),
            structured_log_api_key=(
                os.getenv("FLEETPULSE_XTRA_SHAREPOINT_LOG_API_KEY", "").strip()
                or os.getenv("FLEETPULSE_STRUCTURED_LOG_API_KEY", "").strip()
            ),
            teams_alert_webhook_url=os.getenv("FLEETPULSE_TEAMS_ALERT_WEBHOOK_URL", "").strip(),
            twilio_account_sid=os.getenv("FLEETPULSE_TWILIO_ACCOUNT_SID", "").strip(),
            twilio_auth_token=os.getenv("FLEETPULSE_TWILIO_AUTH_TOKEN", "").strip(),
            twilio_from_number=os.getenv("FLEETPULSE_TWILIO_FROM_NUMBER", "").strip(),
            twilio_to_number=os.getenv("FLEETPULSE_TWILIO_ALERT_TO_NUMBER", "").strip(),
        )

    @property
    def mailbox_configured(self) -> bool:
        return bool(self.mailbox and self.geofence_folder)

    @property
    def graph_configured(self) -> bool:
        return bool(self.graph_tenant_id and self.graph_client_id and self.graph_client_secret)

    @property
    def endpoint_configured(self) -> bool:
        return bool(self.ingestion_api_key)

    @property
    def ingestion_ready(self) -> bool:
        return self.enabled and self.mailbox_configured and self.graph_configured and self.endpoint_configured

    def missing_ingestion_config(self) -> list[str]:
        missing: list[str] = []
        if not self.enabled:
            missing.append("FLEETPULSE_XTRA_INGESTION_ENABLED")
        if not self.mailbox:
            missing.append("FLEETPULSE_XTRA_OUTLOOK_MAILBOX")
        if not self.geofence_folder:
            missing.append("FLEETPULSE_XTRA_GEOFENCE_FOLDER")
        if not self.graph_tenant_id:
            missing.append("FLEETPULSE_GRAPH_TENANT_ID")
        if not self.graph_client_id:
            missing.append("FLEETPULSE_GRAPH_CLIENT_ID")
        if not self.graph_client_secret:
            missing.append("FLEETPULSE_GRAPH_CLIENT_SECRET")
        if not self.ingestion_api_key:
            missing.append("FLEETPULSE_XTRA_INGESTION_API_KEY")
        return missing
