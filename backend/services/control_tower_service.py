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
    ControlTowerTrailersResponse,
    ControlTowerYardLocation,
)
from services.alert_service import get_recent_alerts
from services.fleet_service import LOCATIONS
from services.monitor_service import get_monitor_alerts, get_monitor_status


TRAILER_GROUP_IDS_DEFAULT = "GroupTrailerId"
AR_BUCKETS = ("0-30", "31-60", "61-90", "90+")


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

    xcelerator_event_url_configured = _env_present("FLEETPULSE_XCELERATOR_EVENT_FEED_URL")
    feeds.append(
        _feed(
            "Xcelerator route SLA feed",
            "K1 Group LLC / Xcelerator",
            ControlTowerStatus.WARNING if xcelerator_event_url_configured else ControlTowerStatus.AWAITING_FEED,
            (
                "Xcelerator event feed URL is configured, but the FleetPulse event adapter is not live yet."
                if xcelerator_event_url_configured
                else "Route SLA, paused communications, and workflow exceptions are not wired into this FleetPulse service yet."
            ),
            ["FLEETPULSE_XCELERATOR_EVENT_FEED_URL"],
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


def _is_active_gps(status: dict[str, Any], now: datetime) -> bool:
    timestamp = _status_timestamp(status)
    if not timestamp:
        return False
    stale_hours = int(os.getenv("FLEETPULSE_TRAILER_STATUS_STALE_HOURS", "48"))
    return (now - timestamp).total_seconds() <= stale_hours * 3600


def get_trailers() -> ControlTowerTrailersResponse:
    """Return XTRA/trailer control surface without inventing the Outlook feed."""

    xtra_mail_configured = _env_present("FLEETPULSE_XTRA_OUTLOOK_MAILBOX") and _env_present(
        "FLEETPULSE_XTRA_GEOFENCE_FOLDER"
    )
    feeds: list[ControlTowerFeedStatus] = [
        _feed(
            "XTRA Outlook geofence feed",
            "Outlook / XTRA Lease",
            ControlTowerStatus.WARNING if xtra_mail_configured else ControlTowerStatus.AWAITING_FEED,
            (
                "XTRA Outlook mailbox and folder are configured, but the email ingestion adapter is not live yet."
                if xtra_mail_configured
                else "Trailer geofence email ingestion is not configured in this FleetPulse service yet."
            ),
            ["FLEETPULSE_XTRA_OUTLOOK_MAILBOX", "FLEETPULSE_XTRA_GEOFENCE_FOLDER"],
        )
    ]
    yard_locations = [
        ControlTowerYardLocation(
            name=str(location["name"]),
            latitude=float(location["lat"]),
            longitude=float(location["lon"]),
            trailer_count=0,
        )
        for location in LOCATIONS
    ]
    summary = ControlTowerTrailerSummary(last_email_received=None)

    try:
        group_ids = _csv_env("FLEETPULSE_TRAILER_GROUP_IDS", TRAILER_GROUP_IDS_DEFAULT)
        now = _now()
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
            geofence_events_today=0,
            yards_reporting=sum(1 for yard in yard_locations if yard.trailer_count > 0),
            last_email_received=None,
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
        feeds=feeds,
    )


def get_financial() -> ControlTowerFinancialResponse:
    """Return the K1 Group read-only financial control surface."""

    enabled = _bool_env("FLEETPULSE_FINANCIAL_FEED_ENABLED", False)
    xcelerator_event_url_configured = _env_present("FLEETPULSE_XCELERATOR_EVENT_FEED_URL")
    qbo_feed_configured = _env_present("FLEETPULSE_QBO_FINANCIAL_FEED_URL")
    status = ControlTowerStatus.AWAITING_FEED if not enabled else ControlTowerStatus.WARNING
    message = (
        "Financial feed is not connected to this FleetPulse service yet."
        if not enabled
        else (
            "Financial feed is enabled and source URLs are configured, but the read-only adapter is not live yet."
            if xcelerator_event_url_configured or qbo_feed_configured
            else "Financial feed flag is enabled, but no adapter has been configured."
        )
    )
    return ControlTowerFinancialResponse(
        generated_at=_now(),
        accounts_receivable=[ControlTowerFinancialBucket(bucket=bucket) for bucket in AR_BUCKETS],
        cash_flow={"bank_balance": None, "net_weekly": None, "weekly_income": None, "weekly_expenses": None},
        audit_queue={"pending_audits": 0, "passed_today": 0, "failed_today": 0, "fail_reasons": []},
        feeds=[
            _feed(
                "Xcelerator financial events",
                "K1 Group LLC / Xcelerator",
                status,
                message,
                ["FLEETPULSE_FINANCIAL_FEED_ENABLED", "FLEETPULSE_XCELERATOR_EVENT_FEED_URL"],
            ),
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
            ),
        ],
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
