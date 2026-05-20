"""Machine-readable contracts for scheduled FleetPulse feed orchestration.

Zapier and Power Automate stay as orchestrators. FleetPulse owns only the
read-only import endpoints, validation contracts, and status surfaces.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.seat_kpi_feed_service import FEED_SPECS


def get_scheduled_feed_contracts() -> dict[str, Any]:
    """Return safe POST contracts for external scheduled feed builders."""

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "projection_mode": "read_only",
        "source_authority": "FleetPulse scheduled feed contract registry",
        "auth": {
            "header_alternatives": [
                "X-API-Key",
                "X-FleetPulse-QBO-Key",
                "X-FleetPulse-Xcelerator-Key",
                "X-FleetPulse-HR-Key",
                "X-FleetPulse-Seat-KPI-Key",
            ],
            "credential_storage": "Azure Key Vault App Settings references",
        },
        "feeds": [
            _qbo_financial_contract(),
            _xcelerator_events_contract(),
            _hr_recruiting_contract(),
            *[_seat_feed_contract(key) for key in FEED_SPECS],
        ],
    }


def _base_contract(
    *,
    key: str,
    label: str,
    source_authority: str,
    status_route: str,
    import_route: str,
    auth_header: str,
    state_path_env: str,
    import_key_env: str,
    required_field_groups: list[list[str]],
    accepted_containers: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "source_authority": source_authority,
        "status_route": status_route,
        "import_route": import_route,
        "method": "POST",
        "schedule": "daily",
        "recommended_time": "06:00 America/Chicago",
        "auth_header": auth_header,
        "state_path_env": state_path_env,
        "import_key_env": import_key_env,
        "body_schema": {
            "filename": "string",
            "content": "stringified JSON or CSV export",
            "dry_run": "boolean, optional",
        },
        "accepted_json_containers": accepted_containers or ["rows", "items", "records", "data", "value"],
        "required_field_groups": required_field_groups,
        "source_boundary": "read_only_reference",
    }


def _qbo_financial_contract() -> dict[str, Any]:
    return _base_contract(
        key="qbo_financial",
        label="QBO AP/AR/K1L Expense Snapshot",
        source_authority="QuickBooks Online",
        status_route="/api/fuel/qbo/financial/status",
        import_route="/api/fuel/qbo/financial/import",
        auth_header="X-FleetPulse-QBO-Key",
        state_path_env="FLEETPULSE_QBO_FINANCIAL_STATE_PATH",
        import_key_env="FLEETPULSE_QBO_FINANCIAL_IMPORT_API_KEY",
        required_field_groups=[
            ["qbo_row_kind", "row_kind", "type"],
            ["date", "txn_date", "due_date"],
            ["amount", "balance", "open_balance", "total_amt"],
        ],
    )


def _xcelerator_events_contract() -> dict[str, Any]:
    return _base_contract(
        key="xcelerator_events",
        label="Xcelerator Financial and Exception Events",
        source_authority="K1 Group LLC / Xcelerator event feed",
        status_route="/api/control-tower/xcelerator/events/status",
        import_route="/api/control-tower/xcelerator/events/import",
        auth_header="X-FleetPulse-Xcelerator-Key",
        state_path_env="FLEETPULSE_XCELERATOR_EVENT_STATE_PATH",
        import_key_env="FLEETPULSE_XCELERATOR_EVENT_IMPORT_API_KEY",
        accepted_containers=["events", "items", "rows", "data", "value", "records"],
        required_field_groups=[
            ["event_type", "eventType", "workflow_name", "workflowName", "status"],
            ["timestamp", "updated_at", "created_at"],
            ["shipment_id", "order_id", "route_id", "load_id"],
        ],
    )


def _hr_recruiting_contract() -> dict[str, Any]:
    return _base_contract(
        key="hr_recruiting",
        label="HR Recruiting Worklist Snapshot",
        source_authority="Zapier Table + approved TenStreet Outlook emails",
        status_route="/api/hr-recruiting/status",
        import_route="/api/hr-recruiting/import",
        auth_header="X-FleetPulse-HR-Key",
        state_path_env="HR_RECRUITING_STATE_PATH",
        import_key_env="HR_RECRUITING_IMPORT_API_KEY",
        required_field_groups=[
            ["source_email_id", "Outlook Message ID", "message_id"],
            ["worklist", "Current Worklist", "queue"],
            ["status", "application_status", "lead_status"],
            ["first_assigned_at", "assigned_at", "receivedDateTime", "date"],
        ],
    )


def _seat_feed_contract(feed_key: str) -> dict[str, Any]:
    spec = FEED_SPECS[feed_key]
    return _base_contract(
        key=spec.key,
        label=spec.label,
        source_authority=spec.source_authority,
        status_route=f"/api/control-tower/seat-kpis/feeds/{spec.key}/status",
        import_route=f"/api/control-tower/seat-kpis/feeds/{spec.key}/import",
        auth_header="X-FleetPulse-Seat-KPI-Key",
        state_path_env=spec.state_path_env,
        import_key_env=spec.import_key_env,
        required_field_groups=[list(group) for group in spec.required_groups],
    )
