"""XTRA Lease geofence email ingestion.

This service treats Outlook/XTRA as an external event source. It imports only
read-only event references for the Control Tower trailer projection and never
updates XTRA, Geotab, Xcelerator, or financial source-of-truth data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hmac
import json
import logging
import re
import threading
from typing import Any

from configs.xtra_lease import XtraLeaseIngestionConfig
from integrations.central_logging.http_log_sink import HttpLogSink
from integrations.outlook.graph_client import GraphMailClient, OutlookMessage
from integrations.teams.webhook_client import TeamsWebhookClient
from integrations.twilio.client import TwilioSmsClient
from models import ControlTowerTrailerEvent
from utils.idempotency import stable_idempotency_key

logger = logging.getLogger(__name__)

XTRA_SOURCE_AUTHORITY = "Outlook / XTRA Lease"
_STATE_LOCK = threading.Lock()


class XtraLeaseConfigError(RuntimeError):
    """Raised when the XTRA adapter is called without required configuration."""


@dataclass(frozen=True)
class XtraLeaseProjection:
    events: list[ControlTowerTrailerEvent]
    last_email_received: str | None
    processed_count: int


@dataclass(frozen=True)
class ParsedXtraEmail:
    event: ControlTowerTrailerEvent
    idempotency_key: str


@dataclass(frozen=True)
class XtraLeaseIngestionResult:
    status: str
    fetched_count: int
    imported_count: int
    duplicate_count: int
    invalid_count: int
    last_email_received: str | None
    errors: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_authority": XTRA_SOURCE_AUTHORITY,
            "projection_mode": "read_only",
            "fetched_count": self.fetched_count,
            "imported_count": self.imported_count,
            "duplicate_count": self.duplicate_count,
            "invalid_count": self.invalid_count,
            "last_email_received": self.last_email_received,
            "errors": self.errors,
        }


class XtraLeaseStateStore:
    def __init__(self, config: XtraLeaseIngestionConfig):
        self.config = config
        self.path = config.state_path

    def _empty_state(self) -> dict[str, Any]:
        return {
            "version": 1,
            "processed_idempotency_keys": [],
            "last_email_received": None,
            "events": [],
        }

    def load_state(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty_state()
        with self.path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
        if not isinstance(state, dict):
            raise RuntimeError("xtra_state_invalid")
        state.setdefault("processed_idempotency_keys", [])
        state.setdefault("events", [])
        state.setdefault("last_email_received", None)
        return state

    def save_state(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, sort_keys=True, separators=(",", ":"))
        tmp_path.replace(self.path)

    def projection(self) -> XtraLeaseProjection:
        with _STATE_LOCK:
            state = self.load_state()
        events = [_event_from_raw(raw) for raw in state.get("events", [])]
        events = [event for event in events if event is not None]
        events.sort(key=lambda event: event.timestamp or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return XtraLeaseProjection(
            events=events,
            last_email_received=state.get("last_email_received"),
            processed_count=len(state.get("processed_idempotency_keys", [])),
        )

    def append_events(self, parsed_events: list[ParsedXtraEmail]) -> tuple[int, int, str | None]:
        with _STATE_LOCK:
            state = self.load_state()
            processed_keys = [str(key) for key in state.get("processed_idempotency_keys", [])]
            processed = set(processed_keys)
            events = list(state.get("events", []))
            imported = 0
            duplicates = 0
            newest_received = _parse_optional_datetime(state.get("last_email_received"))

            for parsed in parsed_events:
                if parsed.idempotency_key in processed:
                    duplicates += 1
                    continue
                processed.add(parsed.idempotency_key)
                processed_keys.append(parsed.idempotency_key)
                events.append(parsed.event.model_dump(mode="json"))
                imported += 1
                if parsed.event.timestamp and (newest_received is None or parsed.event.timestamp > newest_received):
                    newest_received = parsed.event.timestamp

            events.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
            state["events"] = events[: self.config.retained_event_limit]
            state["processed_idempotency_keys"] = processed_keys[-self.config.retained_event_limit * 2 :]
            state["last_email_received"] = newest_received.isoformat() if newest_received else state.get("last_email_received")
            self.save_state(state)
            return imported, duplicates, state["last_email_received"]


def _parse_optional_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _event_from_raw(raw: Any) -> ControlTowerTrailerEvent | None:
    if not isinstance(raw, dict):
        return None
    try:
        return ControlTowerTrailerEvent(**raw)
    except Exception:
        logger.warning("xtra_event_state_invalid", extra={"event_id": raw.get("id")})
        return None


def _message_text(message: OutlookMessage) -> str:
    return "\n".join(part for part in [message.subject, message.body_preview] if part)


def _extract_trailer_id(text: str) -> str | None:
    patterns = [
        r"\b(?:trailer|unit|asset|equipment)\s*(?:id|number|no\.?|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]{2,})\b",
        r"\bVIN\s*[:#-]?\s*([A-HJ-NPR-Z0-9]{11,17})\b",
    ]
    upper_text = text.upper()
    for pattern in patterns:
        for match in re.finditer(pattern, upper_text, flags=re.IGNORECASE):
            value = match.group(1).strip(" .,:;")
            if value not in {"XTRA", "LEASE", "GEOFENCE", "TRAILER"}:
                return value
    return None


def _extract_event_type(text: str) -> str:
    lower_text = text.lower()
    if any(term in lower_text for term in ["entered", "arrived", "arrival", "inside geofence", "in geofence"]):
        return "geofence_enter"
    if any(term in lower_text for term in ["exited", "departed", "departure", "left geofence", "outside geofence"]):
        return "geofence_exit"
    return "geofence_event"


def _extract_location(text: str) -> str | None:
    patterns = [
        r"\b(?:geofence|location|site|yard)\s*(?:name)?\s*[:#-]\s*([^\n\r,;]+)",
        r"\b(?:entered|exited|arrived at|departed)\s+([A-Z0-9][A-Z0-9 .'-]{2,60})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip(" .,:;")
            if value:
                return value[:100]
    return None


def parse_xtra_message(message: OutlookMessage, mailbox: str) -> ParsedXtraEmail | None:
    text = _message_text(message)
    trailer_id = _extract_trailer_id(text)
    if not trailer_id:
        return None

    source_message_id = message.internet_message_id or message.id
    key = stable_idempotency_key(
        "xtra_lease_geofence_email_v1",
        mailbox,
        source_message_id,
        message.received_at.isoformat(),
    )
    event = ControlTowerTrailerEvent(
        id=key,
        trailer_id=trailer_id,
        event_type=_extract_event_type(text),
        location=_extract_location(text),
        timestamp=message.received_at,
        source_authority=XTRA_SOURCE_AUTHORITY,
    )
    return ParsedXtraEmail(event=event, idempotency_key=key)


def _validate_ingestion_config(config: XtraLeaseIngestionConfig) -> None:
    missing = config.missing_ingestion_config()
    if missing:
        raise XtraLeaseConfigError(f"xtra_ingestion_missing_config:{','.join(missing)}")


def validate_ingestion_api_key(config: XtraLeaseIngestionConfig, provided_key: str | None) -> None:
    if not config.ingestion_api_key:
        raise XtraLeaseConfigError("xtra_ingestion_api_key_not_configured")
    if not provided_key or not hmac.compare_digest(provided_key, config.ingestion_api_key):
        raise PermissionError("invalid_xtra_ingestion_api_key")


def get_xtra_lease_projection(config: XtraLeaseIngestionConfig | None = None) -> XtraLeaseProjection:
    return XtraLeaseStateStore(config or XtraLeaseIngestionConfig.from_env()).projection()


def _log_payload(
    event_type: str,
    severity: str,
    status: str,
    detail: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "severity": severity,
        "status": status,
        "detail": detail,
        "source_system": "FleetPulse",
        "source_authority": XTRA_SOURCE_AUTHORITY,
        "projection_mode": "read_only",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        **(extra or {}),
    }


def _emit_structured_log(config: XtraLeaseIngestionConfig, payload: dict[str, Any]) -> None:
    log_method = logger.error if payload.get("severity") == "critical" else logger.info
    log_method("xtra_lease_ingestion_event", extra={"xtra_lease": payload})
    sink = HttpLogSink(config.structured_log_url, config.structured_log_api_key, timeout_seconds=config.timeout_seconds)
    if not sink.configured:
        return
    try:
        sink.emit(payload)
    except Exception as exc:
        logger.warning("xtra_structured_log_sink_failed", extra={"error": type(exc).__name__})


def _send_critical_alert(config: XtraLeaseIngestionConfig, message: str) -> None:
    teams = TeamsWebhookClient(config.teams_alert_webhook_url, timeout_seconds=config.timeout_seconds)
    twilio = TwilioSmsClient(
        config.twilio_account_sid,
        config.twilio_auth_token,
        config.twilio_from_number,
        config.twilio_to_number,
        timeout_seconds=config.timeout_seconds,
    )
    for sender in (
        lambda: teams.send("FleetPulse XTRA ingestion failure", message),
        lambda: twilio.send(message),
    ):
        try:
            sender()
        except Exception as exc:
            logger.warning("xtra_alert_sink_failed", extra={"error": type(exc).__name__})


def ingest_xtra_lease_emails(
    config: XtraLeaseIngestionConfig | None = None,
    client: GraphMailClient | None = None,
) -> XtraLeaseIngestionResult:
    config = config or XtraLeaseIngestionConfig.from_env()
    _validate_ingestion_config(config)

    try:
        graph_client = client or GraphMailClient(config)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=config.lookback_hours)
        messages = [message for message in graph_client.list_messages() if message.received_at >= cutoff]
        parsed_events: list[ParsedXtraEmail] = []
        invalid_count = 0
        errors: list[str] = []

        for message in messages:
            parsed = parse_xtra_message(message, config.mailbox)
            if not parsed:
                invalid_count += 1
                errors.append(f"message_missing_trailer_id:{message.id}")
                continue
            parsed_events.append(parsed)

        store = XtraLeaseStateStore(config)
        imported, duplicates, last_email_received = store.append_events(parsed_events)
        result = XtraLeaseIngestionResult(
            status="ok",
            fetched_count=len(messages),
            imported_count=imported,
            duplicate_count=duplicates,
            invalid_count=invalid_count,
            last_email_received=last_email_received,
            errors=errors[:10],
        )
        _emit_structured_log(
            config,
            _log_payload(
                "fleetpulse.xtra_lease.ingestion",
                "info",
                "ok",
                "XTRA Outlook geofence feed ingested.",
                result.as_dict(),
            ),
        )
        return result
    except Exception as exc:
        payload = _log_payload(
            "fleetpulse.xtra_lease.ingestion",
            "critical",
            "failed",
            f"XTRA Outlook geofence ingestion failed: {type(exc).__name__}",
            {"error_type": type(exc).__name__},
        )
        _emit_structured_log(config, payload)
        _send_critical_alert(config, payload["detail"])
        raise
