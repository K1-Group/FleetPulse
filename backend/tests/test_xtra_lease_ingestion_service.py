"""Tests for XTRA Lease Outlook ingestion."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from configs.xtra_lease import XtraLeaseIngestionConfig  # noqa: E402
from integrations.outlook.graph_client import OutlookMessage  # noqa: E402
from services.xtra_lease_ingestion_service import (  # noqa: E402
    get_xtra_lease_projection,
    ingest_xtra_lease_emails,
)


class FakeGraphClient:
    def __init__(self, messages: list[OutlookMessage]):
        self._messages = messages

    def list_messages(self) -> list[OutlookMessage]:
        return self._messages


def _configure_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEETPULSE_XTRA_INGESTION_ENABLED", "true")
    monkeypatch.setenv("FLEETPULSE_XTRA_OUTLOOK_MAILBOX", "xtra@example.com")
    monkeypatch.setenv("FLEETPULSE_XTRA_GEOFENCE_FOLDER", "XTRA Lease Trailer Geofence Tracker")
    monkeypatch.setenv("FLEETPULSE_XTRA_INGESTION_API_KEY", "expected")
    monkeypatch.setenv("FLEETPULSE_GRAPH_TENANT_ID", "tenant")
    monkeypatch.setenv("FLEETPULSE_GRAPH_CLIENT_ID", "client")
    monkeypatch.setenv("FLEETPULSE_GRAPH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("FLEETPULSE_XTRA_STATE_PATH", str(tmp_path / "xtra-state.json"))
    monkeypatch.setenv("FLEETPULSE_XTRA_LOOKBACK_HOURS", "72")
    return XtraLeaseIngestionConfig.from_env()


def test_ingestion_ignores_duplicates_and_updates_last_email(monkeypatch, tmp_path):
    config = _configure_env(monkeypatch, tmp_path)
    first_received = datetime(2026, 5, 12, 2, 0, tzinfo=timezone.utc)
    second_received = datetime(2026, 5, 12, 3, 15, tzinfo=timezone.utc)
    first = OutlookMessage(
        id="graph-1",
        internet_message_id="<xtra-1@example.com>",
        subject="Trailer ABC123 entered Fort Worth Yard geofence",
        body_preview="Trailer ID ABC123\nGeofence: Fort Worth Yard",
        received_at=first_received,
    )
    second = OutlookMessage(
        id="graph-2",
        internet_message_id="<xtra-2@example.com>",
        subject="Unit ZX987 exited Kansas City Yard geofence",
        body_preview="Unit ZX987 departed Kansas City Yard",
        received_at=second_received,
    )

    first_result = ingest_xtra_lease_emails(config, client=FakeGraphClient([first]))
    second_result = ingest_xtra_lease_emails(config, client=FakeGraphClient([first, second]))
    projection = get_xtra_lease_projection(config)

    assert first_result.imported_count == 1
    assert first_result.duplicate_count == 0
    assert second_result.imported_count == 1
    assert second_result.duplicate_count == 1
    assert second_result.last_email_received == second_received.isoformat()
    assert len(projection.events) == 2
    assert projection.events[0].trailer_id == "ZX987"
    assert projection.events[0].event_type == "geofence_exit"
    assert projection.last_email_received == second_received.isoformat()
