"""Read-only Control Tower projections for FleetPulse.

These endpoints restore the original Control Tower dashboard surfaces without
making FleetPulse authoritative for Xcelerator, finance, or external automation
systems. Missing upstream feeds are reported as awaiting configuration instead
of being filled with sample numbers.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any

import httpx

from configs.xtra_lease import XtraLeaseIngestionConfig
from geotab_client import GeotabClient
from models import (
    Alert,
    AlertSeverity,
    ControlTowerAgentFlow,
    ControlTowerAgentsResponse,
    ControlTowerAgentSystem,
    ControlTowerAttentionItem,
    ControlTowerAttentionResponse,
    ControlTowerCodexResponse,
    ControlTowerFeedStatus,
    ControlTowerFinancialBucket,
    ControlTowerFinancialResponse,
    ControlTowerOverview,
    ControlTowerSectionSummary,
    ControlTowerStatus,
    ControlTowerTrailerSummary,
    ControlTowerTrailerEvent,
    ControlTowerTrailersResponse,
    ControlTowerYardLocation,
)
from services.alert_service import get_recent_alerts
from services.fleet_service import LOCATIONS
from services.monitor_service import get_monitor_alerts, get_monitor_status
from services.xcelerator_gross_margin_service import get_xcelerator_gross_margin_snapshot
from services.xtra_lease_ingestion_service import XtraLeaseProjection, get_xtra_lease_projection


TRAILER_GROUP_IDS_DEFAULT = "GroupTrailerId"
AR_BUCKETS = ("0-30", "31-60", "61-90", "90+")
XCELERATOR_SOURCE_AUTHORITY = "K1 Group LLC / Xcelerator"
XCELERATOR_EVENT_FEED_ENV = "FLEETPULSE_XCELERATOR_EVENT_FEED_URL"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _env_present(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str, default: str = "") -> set[str]:
    return {item.strip() for item in os.getenv(name, default).split(",") if item.strip()}


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _humanize(value: Any) -> str:
    text = str(value or "").replace("_", " ").replace("-", " ").strip()
    return " ".join(part.capitalize() for part in text.split()) if text else ""


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _first_value(record: dict[str, Any], *names: str) -> Any:
    sources = [
        record,
        record.get("metadata") if isinstance(record.get("metadata"), dict) else {},
        record.get("source_payload") if isinstance(record.get("source_payload"), dict) else {},
        record.get("references") if isinstance(record.get("references"), dict) else {},
    ]
    for source in sources:
        for name in names:
            value = source.get(name)
            if value not in (None, ""):
                return value
    return None


def _coerce_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("events", "items", "rows", "data", "value", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    tables = payload.get("tables")
    if isinstance(tables, dict):
        for value in tables.values():
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _xcelerator_event_feed_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    api_key = os.getenv("FLEETPULSE_XCELERATOR_EVENT_FEED_API_KEY", "").strip()
    if api_key:
        header_name = (
            os.getenv("FLEETPULSE_XCELERATOR_EVENT_FEED_API_KEY_HEADER", "").strip()
            or "X-FleetPulse-Xcelerator-Key"
        )
        headers[header_name] = api_key
    return headers


def _fetch_xcelerator_event_rows() -> tuple[list[dict[str, Any]], datetime | None]:
    url = os.getenv(XCELERATOR_EVENT_FEED_ENV, "").strip()
    if not url:
        return [], None
    timeout = _float_env("FLEETPULSE_XCELERATOR_EVENT_FEED_TIMEOUT_SECONDS", 15.0)
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url, headers=_xcelerator_event_feed_headers())
    response.raise_for_status()
    payload = response.json()
    rows = _coerce_rows(payload)
    last_updated = _parse_datetime(
        payload.get("last_updated")
        or payload.get("lastUpdated")
        or payload.get("generated_at")
        or payload.get("generatedAt")
    ) if isinstance(payload, dict) else None
    if last_updated is None:
        row_timestamps = [
            timestamp
            for row in rows
            if (
                timestamp := _parse_datetime(
                    _first_value(
                        row,
                        "timestamp",
                        "updated_at",
                        "updatedAt",
                        "created_at",
                        "createdAt",
                        "detected_at",
                        "detectedAt",
                    )
                )
            )
        ]
        last_updated = max(row_timestamps, default=None)
    return rows, last_updated


def _xcelerator_review_orders_evidence() -> dict[str, Any] | None:
    path = (
        os.getenv("FLEETPULSE_XCELERATOR_REVIEW_ORDERS_STATE_PATH", "").strip()
        or os.getenv("FLEETPULSE_LANE_STABILITY_ORDER_FEED_PATH", "").strip()
    )
    if not path:
        return None
    try:
        stat = os.stat(path)
    except FileNotFoundError:
        return {
            "status": ControlTowerStatus.AWAITING_FEED,
            "message": "Xcelerator ReviewOrders evidence path is configured, but no rows have been imported yet.",
            "last_updated": None,
        }
    except OSError as exc:
        return {
            "status": ControlTowerStatus.UNAVAILABLE,
            "message": f"Xcelerator ReviewOrders evidence unavailable: {type(exc).__name__}",
            "last_updated": None,
        }

    if stat.st_size <= 2:
        return {
            "status": ControlTowerStatus.AWAITING_FEED,
            "message": "Xcelerator ReviewOrders evidence file is empty.",
            "last_updated": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        }

    return {
        "status": ControlTowerStatus.HEALTHY,
        "message": f"Xcelerator ReviewOrders evidence file is available ({stat.st_size:,} bytes).",
        "last_updated": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
    }


def _xcelerator_event_severity(record: dict[str, Any]) -> AlertSeverity:
    value = str(_first_value(record, "severity", "priority", "alert_level", "alertLevel") or "").lower()
    status = str(_first_value(record, "status", "exception_status", "exceptionStatus") or "").lower()
    event_type = str(_first_value(record, "event_type", "eventType", "workflow_name", "workflowName") or "").lower()
    if value in {severity.value for severity in AlertSeverity}:
        return AlertSeverity(value)
    if status in {"critical", "failed", "failure", "exception"} or "exception" in event_type:
        return AlertSeverity.HIGH
    if status in {"late", "missed", "overdue", "open", "pending", "warning"}:
        return AlertSeverity.MEDIUM
    return AlertSeverity.LOW


def _is_xcelerator_attention_record(record: dict[str, Any]) -> bool:
    status = str(_first_value(record, "status", "exception_status", "exceptionStatus") or "").lower()
    event_type = str(_first_value(record, "event_type", "eventType", "workflow_name", "workflowName") or "").lower()
    if status in {"exception", "failed", "failure", "late", "missed", "overdue", "open", "pending"}:
        return True
    return any(token in event_type for token in ("exception", "missed", "route_check_in", "check_in"))


def _xcelerator_attention_item(record: dict[str, Any], index: int) -> ControlTowerAttentionItem:
    severity = _xcelerator_event_severity(record)
    event_type = _first_value(record, "event_type", "eventType", "workflow_name", "workflowName")
    route_id = _first_value(record, "route_id", "routeId", "route_number", "routeNumber")
    shipment_id = _first_value(record, "shipment_id", "shipmentId", "load_id", "loadId")
    record_id = (
        _first_value(record, "id", "event_id", "eventId", "route_exception_id", "routeExceptionId")
        or route_id
        or shipment_id
        or f"xcelerator-{index}"
    )
    timestamp = _parse_datetime(
        _first_value(
            record,
            "timestamp",
            "updated_at",
            "updatedAt",
            "created_at",
            "createdAt",
            "detected_at",
            "detectedAt",
        )
    )
    message = _first_value(record, "message", "summary", "description", "detail")
    if not message:
        target = route_id or shipment_id or "Xcelerator event"
        message = f"{_humanize(event_type) or 'Xcelerator event'} requires review for {target}."
    category = "Linehaul" if route_id else "Dispatch" if shipment_id else "Xcelerator"
    action = "Escalate" if severity == AlertSeverity.CRITICAL else "Review" if severity in {AlertSeverity.HIGH, AlertSeverity.MEDIUM} else "Monitor"
    return ControlTowerAttentionItem(
        id=f"xcelerator:{record_id}",
        category=category,
        severity=severity,
        action=action,
        message=str(message),
        source_authority=XCELERATOR_SOURCE_AUTHORITY,
        timestamp=timestamp,
    )


def _feed(
    name: str,
    source_authority: str,
    status: ControlTowerStatus,
    message: str,
    required_config: list[str] | None = None,
    last_updated: datetime | None = None,
) -> ControlTowerFeedStatus:
    return ControlTowerFeedStatus(
        name=name,
        source_authority=source_authority,
        status=status,
        message=message,
        required_config=required_config or [],
        last_updated=last_updated,
    )


def _control_tower_status(value: str) -> ControlTowerStatus:
    if value in {status.value for status in ControlTowerStatus}:
        return ControlTowerStatus(value)
    if value == "partial":
        return ControlTowerStatus.WARNING
    return ControlTowerStatus.AWAITING_FEED


def _alert_to_attention(alert: Alert, source_authority: str) -> ControlTowerAttentionItem:
    severity = alert.severity
    if severity == AlertSeverity.CRITICAL:
        action = "Escalate"
    elif severity == AlertSeverity.HIGH:
        action = "Review"
    else:
        action = "Monitor"

    return ControlTowerAttentionItem(
        id=alert.id,
        category=alert.alert_type or "Fleet",
        severity=severity,
        action=action,
        message=alert.message,
        source_authority=source_authority,
        timestamp=alert.timestamp,
    )


def get_attention() -> ControlTowerAttentionResponse:
    """Return the operator exception queue across available read-only feeds."""

    feeds: list[ControlTowerFeedStatus] = []
    items_by_id: dict[str, ControlTowerAttentionItem] = {}

    try:
        for alert in get_recent_alerts(hours=24):
            item = _alert_to_attention(alert, "Geotab")
            items_by_id[item.id] = item
        feeds.append(
            _feed(
                "Geotab exception events",
                "K1 Logistics Inc / Geotab",
                ControlTowerStatus.HEALTHY,
                "Live Geotab exception feed queried for fleet alerts.",
            )
        )
    except Exception as exc:
        feeds.append(
            _feed(
                "Geotab exception events",
                "K1 Logistics Inc / Geotab",
                ControlTowerStatus.UNAVAILABLE,
                f"Geotab exception feed unavailable: {type(exc).__name__}",
            )
        )

    try:
        for alert in get_monitor_alerts(limit=50):
            item = _alert_to_attention(alert, "FleetPulse monitor")
            items_by_id[item.id] = item
        monitor_status = get_monitor_status()
        status = ControlTowerStatus.HEALTHY if monitor_status.get("running") else ControlTowerStatus.WARNING
        feeds.append(
            _feed(
                "FleetPulse monitor",
                "K1 Logistics Inc / Geotab",
                status,
                "Monitor is running." if monitor_status.get("running") else "Monitor is configured but not running.",
            )
        )
    except Exception as exc:
        feeds.append(
            _feed(
                "FleetPulse monitor",
                "K1 Logistics Inc / Geotab",
                ControlTowerStatus.UNAVAILABLE,
                f"Monitor status unavailable: {type(exc).__name__}",
            )
        )

    if _env_present(XCELERATOR_EVENT_FEED_ENV):
        try:
            xcelerator_rows, xcelerator_last_updated = _fetch_xcelerator_event_rows()
            attention_rows = [
                row for row in xcelerator_rows if _is_xcelerator_attention_record(row)
            ]
            for index, row in enumerate(attention_rows, start=1):
                item = _xcelerator_attention_item(row, index)
                items_by_id[item.id] = item
            status = (
                ControlTowerStatus.HEALTHY
                if xcelerator_rows
                else ControlTowerStatus.AWAITING_FEED
            )
            feeds.append(
                _feed(
                    "Xcelerator route SLA feed",
                    XCELERATOR_SOURCE_AUTHORITY,
                    status,
                    (
                        f"Read {len(xcelerator_rows)} Xcelerator event row(s); "
                        f"{len(attention_rows)} require attention."
                        if xcelerator_rows
                        else "Xcelerator event feed is reachable but returned no rows."
                    ),
                    [XCELERATOR_EVENT_FEED_ENV],
                    xcelerator_last_updated,
                )
            )
        except Exception as exc:
            feeds.append(
                _feed(
                    "Xcelerator route SLA feed",
                    XCELERATOR_SOURCE_AUTHORITY,
                    ControlTowerStatus.UNAVAILABLE,
                    f"Xcelerator event feed unavailable: {type(exc).__name__}",
                    [XCELERATOR_EVENT_FEED_ENV],
                )
            )
    else:
        feeds.append(
            _feed(
                "Xcelerator route SLA feed",
                XCELERATOR_SOURCE_AUTHORITY,
                ControlTowerStatus.AWAITING_FEED,
                "Route SLA, paused communications, and workflow exceptions are not wired into this FleetPulse service yet.",
                [XCELERATOR_EVENT_FEED_ENV],
            )
        )

    severity_rank = {
        AlertSeverity.CRITICAL: 4,
        AlertSeverity.HIGH: 3,
        AlertSeverity.MEDIUM: 2,
        AlertSeverity.LOW: 1,
    }
    items = sorted(
        items_by_id.values(),
        key=lambda item: (severity_rank.get(item.severity, 0), item.timestamp or datetime.min.replace(tzinfo=timezone.utc)),
        reverse=True,
    )

    return ControlTowerAttentionResponse(generated_at=_now(), items=items[:50], feeds=feeds)


def _device_group_ids(device: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for group in device.get("groups") or []:
        if isinstance(group, dict):
            value = group.get("id") or group.get("name")
        else:
            value = group
        if value:
            values.add(str(value))
    return values


def _status_timestamp(status: dict[str, Any]) -> datetime | None:
    raw = status.get("dateTime")
    if isinstance(raw, datetime):
        return raw.astimezone(timezone.utc) if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _parse_iso_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _is_active_gps(status: dict[str, Any], now: datetime) -> bool:
    timestamp = _status_timestamp(status)
    if not timestamp:
        return False
    stale_hours = int(os.getenv("FLEETPULSE_TRAILER_STATUS_STALE_HOURS", "48"))
    return (now - timestamp).total_seconds() <= stale_hours * 3600


def _count_events_today(events: list[ControlTowerTrailerEvent], now: datetime) -> int:
    today = now.astimezone(timezone.utc).date()
    return sum(1 for event in events if event.timestamp and event.timestamp.astimezone(timezone.utc).date() == today)


def _xtra_feed_status(
    config: XtraLeaseIngestionConfig,
    projection: XtraLeaseProjection | None,
    error: str | None = None,
) -> ControlTowerFeedStatus:
    if not config.mailbox_configured:
        return _feed(
            "XTRA Outlook geofence feed",
            "Outlook / XTRA Lease",
            ControlTowerStatus.AWAITING_FEED,
            "Trailer geofence email ingestion is not configured in this FleetPulse service yet.",
            ["FLEETPULSE_XTRA_OUTLOOK_MAILBOX", "FLEETPULSE_XTRA_GEOFENCE_FOLDER"],
        )
    if not config.enabled:
        return _feed(
            "XTRA Outlook geofence feed",
            "Outlook / XTRA Lease",
            ControlTowerStatus.WARNING,
            "XTRA Outlook mailbox and folder are configured, but ingestion is not enabled yet.",
            ["FLEETPULSE_XTRA_INGESTION_ENABLED"],
        )
    missing = config.missing_ingestion_config()
    if missing:
        return _feed(
            "XTRA Outlook geofence feed",
            "Outlook / XTRA Lease",
            ControlTowerStatus.WARNING,
            "XTRA ingestion is enabled, but required Graph or endpoint configuration is missing.",
            missing,
        )
    if error:
        return _feed(
            "XTRA Outlook geofence feed",
            "Outlook / XTRA Lease",
            ControlTowerStatus.UNAVAILABLE,
            f"XTRA ingestion state unavailable: {error}",
            ["FLEETPULSE_XTRA_STATE_PATH"],
        )
    last_updated = _parse_iso_datetime(projection.last_email_received if projection else None)
    if last_updated:
        return _feed(
            "XTRA Outlook geofence feed",
            "Outlook / XTRA Lease",
            ControlTowerStatus.HEALTHY,
            "XTRA Outlook ingestion adapter is live and importing geofence email events.",
            last_updated=last_updated,
        )
    return _feed(
        "XTRA Outlook geofence feed",
        "Outlook / XTRA Lease",
        ControlTowerStatus.WARNING,
        "XTRA Outlook ingestion adapter is live, but no geofence emails have been imported yet.",
    )


def get_trailers() -> ControlTowerTrailersResponse:
    """Return XTRA/trailer control surface without inventing the Outlook feed."""

    xtra_config = XtraLeaseIngestionConfig.from_env()
    geofence_events: list[ControlTowerTrailerEvent] = []
    last_email_received: str | None = None
    xtra_projection: XtraLeaseProjection | None = None
    xtra_error: str | None = None
    try:
        xtra_projection = get_xtra_lease_projection(xtra_config)
        geofence_events = xtra_projection.events[:50]
        last_email_received = xtra_projection.last_email_received
    except Exception as exc:
        xtra_error = type(exc).__name__
    feeds: list[ControlTowerFeedStatus] = [_xtra_feed_status(xtra_config, xtra_projection, xtra_error)]
    yard_locations = [
        ControlTowerYardLocation(
            name=str(location["name"]),
            latitude=float(location["lat"]),
            longitude=float(location["lon"]),
            trailer_count=0,
        )
        for location in LOCATIONS
    ]
    now = _now()
    geofence_events_today = _count_events_today(geofence_events, now)
    summary = ControlTowerTrailerSummary(
        geofence_events_today=geofence_events_today,
        last_email_received=last_email_received,
    )

    try:
        group_ids = _csv_env("FLEETPULSE_TRAILER_GROUP_IDS", TRAILER_GROUP_IDS_DEFAULT)
        client = GeotabClient.get()
        devices = [
            device
            for device in client.get_devices()
            if _device_group_ids(device).intersection(group_ids)
        ]
        statuses = client.get_device_status_info()
        status_by_device = {status.get("device", {}).get("id"): status for status in statuses}
        active = 0
        inactive = 0
        for device in devices:
            status = status_by_device.get(device.get("id"), {})
            if _is_active_gps(status, now):
                active += 1
                lat = status.get("latitude") or 0
                lon = status.get("longitude") or 0
                for yard in yard_locations:
                    distance = ((lat - yard.latitude) ** 2 + (lon - yard.longitude) ** 2) ** 0.5
                    if distance < 0.005:
                        yard.trailer_count += 1
                        break
            else:
                inactive += 1

        summary = ControlTowerTrailerSummary(
            total_trailers=len(devices),
            gps_active=active,
            gps_inactive=inactive,
            geofence_events_today=geofence_events_today,
            yards_reporting=sum(1 for yard in yard_locations if yard.trailer_count > 0),
            last_email_received=last_email_received,
        )
        feeds.append(
            _feed(
                "Geotab trailer device group",
                "K1 Logistics Inc / Geotab",
                ControlTowerStatus.HEALTHY,
                f"Trailer device group projection loaded from {','.join(sorted(group_ids))}.",
            )
        )
    except Exception as exc:
        feeds.append(
            _feed(
                "Geotab trailer device group",
                "K1 Logistics Inc / Geotab",
                ControlTowerStatus.UNAVAILABLE,
                f"Trailer device group unavailable: {type(exc).__name__}",
                ["FLEETPULSE_TRAILER_GROUP_IDS"],
            )
        )

    return ControlTowerTrailersResponse(
        generated_at=_now(),
        summary=summary,
        yard_locations=yard_locations,
        geofence_events=geofence_events,
        feeds=feeds,
    )


def get_financial() -> ControlTowerFinancialResponse:
    """Return the K1 Group read-only financial control surface."""

    enabled = _bool_env("FLEETPULSE_FINANCIAL_FEED_ENABLED", False)
    xcelerator_event_url_configured = _env_present(XCELERATOR_EVENT_FEED_ENV)
    qbo_feed_configured = _env_present("FLEETPULSE_QBO_FINANCIAL_FEED_URL")
    xcelerator_status = ControlTowerStatus.AWAITING_FEED
    xcelerator_message = "Financial feed is not connected to this FleetPulse service yet."
    xcelerator_last_updated: datetime | None = None
    xcelerator_required_config = ["FLEETPULSE_FINANCIAL_FEED_ENABLED", XCELERATOR_EVENT_FEED_ENV]
    xcelerator_event_error: Exception | None = None
    gross_margin_snapshot: dict[str, Any] | None = None
    if enabled and xcelerator_event_url_configured:
        try:
            xcelerator_rows, xcelerator_last_updated = _fetch_xcelerator_event_rows()
            financial_rows = [
                row
                for row in xcelerator_rows
                if _first_value(
                    row,
                    "revenue_amount",
                    "revenueAmount",
                    "driver_pay_amount",
                    "driverPayAmount",
                    "gross_margin",
                    "grossMargin",
                )
                is not None
            ]
            xcelerator_status = (
                ControlTowerStatus.HEALTHY
                if financial_rows
                else ControlTowerStatus.WARNING
            )
            xcelerator_message = (
                f"Read {len(xcelerator_rows)} Xcelerator row(s); "
                f"{len(financial_rows)} financial row(s) are available for read-only projection."
            )
        except Exception as exc:
            xcelerator_event_error = exc
    elif enabled:
        xcelerator_message = "Financial feed flag is enabled, but no Xcelerator event feed URL is configured."
    if enabled and xcelerator_status != ControlTowerStatus.HEALTHY:
        evidence = _xcelerator_review_orders_evidence()
        if evidence:
            xcelerator_status = evidence["status"]
            xcelerator_last_updated = evidence["last_updated"]
            xcelerator_required_config = [
                "FLEETPULSE_FINANCIAL_FEED_ENABLED",
                "FLEETPULSE_XCELERATOR_REVIEW_ORDERS_STATE_PATH",
            ]
            xcelerator_message = evidence["message"]
            if xcelerator_event_error and xcelerator_status == ControlTowerStatus.HEALTHY:
                xcelerator_message = (
                    f"{xcelerator_message} Event feed URL is not a readable row feed "
                    f"({type(xcelerator_event_error).__name__}); using persisted Xcelerator evidence."
                )
        elif xcelerator_event_error:
            xcelerator_status = ControlTowerStatus.UNAVAILABLE
            xcelerator_message = f"Xcelerator financial event feed unavailable: {type(xcelerator_event_error).__name__}"
    if enabled:
        gross_margin_snapshot = get_xcelerator_gross_margin_snapshot()
        if (
            gross_margin_snapshot.get("status") in {"healthy", "partial"}
            and xcelerator_status != ControlTowerStatus.HEALTHY
        ):
            xcelerator_status = _control_tower_status(str(gross_margin_snapshot.get("status")))
            xcelerator_message = gross_margin_snapshot.get("message") or xcelerator_message
            xcelerator_last_updated = _parse_datetime(gross_margin_snapshot.get("last_updated")) or xcelerator_last_updated
            xcelerator_required_config = gross_margin_snapshot.get("required_config") or xcelerator_required_config
    feeds = [
        _feed(
            "Xcelerator financial events",
            XCELERATOR_SOURCE_AUTHORITY,
            xcelerator_status,
            xcelerator_message,
            xcelerator_required_config,
            xcelerator_last_updated,
        )
    ]
    if gross_margin_snapshot:
        feeds.append(
            _feed(
                "Xcelerator gross margin",
                gross_margin_snapshot.get("source_authority") or XCELERATOR_SOURCE_AUTHORITY,
                _control_tower_status(str(gross_margin_snapshot.get("status"))),
                str(gross_margin_snapshot.get("message") or "Xcelerator gross margin projection is awaiting rows."),
                list(gross_margin_snapshot.get("required_config") or []),
                _parse_datetime(gross_margin_snapshot.get("last_updated")),
            )
        )
    feeds.append(
        _feed(
            "QuickBooks AR/AP snapshots",
            "K1 Group LLC / QuickBooks",
            ControlTowerStatus.WARNING if qbo_feed_configured else ControlTowerStatus.AWAITING_FEED,
            (
                "QuickBooks financial feed URL is configured, but the read-only adapter is not live yet."
                if qbo_feed_configured
                else "QuickBooks financial snapshots are not connected to this FleetPulse service yet."
            ),
            ["FLEETPULSE_QBO_FINANCIAL_FEED_URL"],
        )
    )
    return ControlTowerFinancialResponse(
        generated_at=_now(),
        accounts_receivable=[ControlTowerFinancialBucket(bucket=bucket) for bucket in AR_BUCKETS],
        cash_flow={"bank_balance": None, "net_weekly": None, "weekly_income": None, "weekly_expenses": None},
        audit_queue={"pending_audits": 0, "passed_today": 0, "failed_today": 0, "fail_reasons": []},
        gross_margin=gross_margin_snapshot,
        feeds=feeds,
    )


def _configured_flow(name: str, env_names: list[str], configured_detail: str) -> ControlTowerAgentFlow:
    configured = all(_env_present(env_name) for env_name in env_names)
    return ControlTowerAgentFlow(
        name=name,
        status=ControlTowerStatus.HEALTHY if configured else ControlTowerStatus.AWAITING_FEED,
        detail=configured_detail if configured else f"Awaiting {', '.join(env_names)}.",
    )


def get_agents() -> ControlTowerAgentsResponse:
    """Return automation system readiness without exposing secrets."""

    monitor = get_monitor_status()
    monitor_running = bool(monitor.get("running"))
    systems = [
        ControlTowerAgentSystem(
            name="Zapier",
            status=ControlTowerStatus.HEALTHY
            if _bool_env("FLEETPULSE_ZAPIER_ENABLED") and _env_present("FLEETPULSE_ZAPIER_WEBHOOK_URL")
            else ControlTowerStatus.AWAITING_FEED,
            flows=[
                _configured_flow(
                    "Fleet snapshot Teams notification",
                    ["FLEETPULSE_ZAPIER_WEBHOOK_URL", "FLEETPULSE_ZAPIER_SHARED_SECRET"],
                    "Webhook and HMAC shared secret are configured.",
                )
            ],
        ),
        ControlTowerAgentSystem(
            name="FleetPulse Monitor",
            status=ControlTowerStatus.HEALTHY if monitor_running else ControlTowerStatus.WARNING,
            flows=[
                ControlTowerAgentFlow(
                    name="Geotab anomaly scan",
                    status=ControlTowerStatus.HEALTHY if monitor_running else ControlTowerStatus.WARNING,
                    detail="Background monitor is running." if monitor_running else "Background monitor is disabled.",
                )
            ],
        ),
        ControlTowerAgentSystem(
            name="Power Automate",
            status=ControlTowerStatus.HEALTHY
            if _bool_env("FLEETPULSE_POWER_AUTOMATE_ENABLED")
            else ControlTowerStatus.AWAITING_FEED,
            flows=[
                _configured_flow(
                    "Dispatch visibility approval",
                    ["FLEETPULSE_POWER_AUTOMATE_FLOW_URL"],
                    "Approval flow endpoint is configured.",
                )
            ],
        ),
        ControlTowerAgentSystem(
            name="Copilot Studio",
            status=ControlTowerStatus.HEALTHY
            if _bool_env("FLEETPULSE_COPILOT_ENABLED")
            else ControlTowerStatus.AWAITING_FEED,
            flows=[
                _configured_flow(
                    "Supervisor escalation",
                    ["FLEETPULSE_COPILOT_AGENT_URL"],
                    "Supervisor agent endpoint is configured.",
                )
            ],
        ),
        ControlTowerAgentSystem(
            name="OpenRouter AI",
            status=ControlTowerStatus.HEALTHY if _env_present("OPENROUTER_API_KEY") else ControlTowerStatus.AWAITING_FEED,
            flows=[
                _configured_flow(
                    "Fleet AI chat",
                    ["OPENROUTER_API_KEY", "OPENROUTER_MODEL"],
                    "OpenRouter model and API key are configured.",
                )
            ],
        ),
    ]
    return ControlTowerAgentsResponse(generated_at=_now(), systems=systems)


def get_codex() -> ControlTowerCodexResponse:
    """Return CI/repo execution context when the app runs inside GitHub Actions."""

    repository = os.getenv("GITHUB_REPOSITORY") or os.getenv("FLEETPULSE_REPOSITORY")
    commit_sha = os.getenv("GITHUB_SHA")
    branch = os.getenv("GITHUB_REF_NAME") or os.getenv("GITHUB_REF")
    run_id = os.getenv("GITHUB_RUN_ID")
    configured = bool(repository or commit_sha or run_id)
    return ControlTowerCodexResponse(
        generated_at=_now(),
        overall_status=ControlTowerStatus.HEALTHY if configured else ControlTowerStatus.AWAITING_FEED,
        repository=repository,
        branch=branch,
        commit_sha=commit_sha[:12] if commit_sha else None,
        run_id=run_id,
        message=(
            "GitHub Actions runtime context is available."
            if configured
            else "Codex/GitHub telemetry is not connected in this runtime."
        ),
        feeds=[
            _feed(
                "GitHub Actions context",
                "GitHub",
                ControlTowerStatus.HEALTHY if configured else ControlTowerStatus.AWAITING_FEED,
                "Runtime exposes repository metadata." if configured else "Awaiting GitHub Actions runtime metadata.",
                ["GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_RUN_ID"],
            )
        ],
    )


def get_overview() -> ControlTowerOverview:
    attention = get_attention()
    trailers = get_trailers()
    financial = get_financial()
    agents = get_agents()
    codex = get_codex()

    def feed_rollup(feeds: list[ControlTowerFeedStatus]) -> ControlTowerStatus:
        if any(feed.status == ControlTowerStatus.CRITICAL for feed in feeds):
            return ControlTowerStatus.CRITICAL
        if any(feed.status == ControlTowerStatus.UNAVAILABLE for feed in feeds):
            return ControlTowerStatus.WARNING
        if any(feed.status == ControlTowerStatus.HEALTHY for feed in feeds):
            return ControlTowerStatus.HEALTHY
        return ControlTowerStatus.AWAITING_FEED

    sections = [
        ControlTowerSectionSummary(
            key="attention",
            label="Attention",
            status=feed_rollup(attention.feeds),
            source_authority="Geotab + Xcelerator event projections",
            item_count=len(attention.items),
            message="Unified exception queue.",
        ),
        ControlTowerSectionSummary(
            key="trailers",
            label="Trailers",
            status=feed_rollup(trailers.feeds),
            source_authority="Geotab + Outlook/XTRA",
            item_count=trailers.summary.total_trailers,
            message="Trailer GPS and geofence feed.",
        ),
        ControlTowerSectionSummary(
            key="financial",
            label="Financial",
            status=feed_rollup(financial.feeds),
            source_authority=financial.source_authority,
            item_count=financial.accounts_payable.pending_bills,
            message="Read-only AP/AR and cash-flow projection.",
        ),
        ControlTowerSectionSummary(
            key="agents",
            label="Agents",
            status=ControlTowerStatus.HEALTHY
            if any(system.status == ControlTowerStatus.HEALTHY for system in agents.systems)
            else ControlTowerStatus.AWAITING_FEED,
            source_authority="Zapier / Power Automate / Copilot / FleetPulse",
            item_count=len(agents.systems),
            message="Automation system health.",
        ),
        ControlTowerSectionSummary(
            key="codex",
            label="Codex",
            status=codex.overall_status,
            source_authority="GitHub",
            item_count=1 if codex.repository else 0,
            message=codex.message,
        ),
    ]
    return ControlTowerOverview(generated_at=_now(), sections=sections)
