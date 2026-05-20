"""Tests for scheduled seat KPI feed state."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services.seat_kpi_feed_service import (  # noqa: E402
    FEED_SPECS,
    SeatKpiFeedStateStore,
    get_seat_kpi_feed_status,
    import_seat_kpi_feed,
    parse_seat_kpi_feed_content,
)


def test_billing_exception_import_is_idempotent(tmp_path) -> None:
    state_path = tmp_path / "billing-exceptions.json"
    store = SeatKpiFeedStateStore(FEED_SPECS["billing_exceptions"], state_path)
    content = json.dumps(
        {
            "rows": [
                {
                    "exception_id": "BE-100",
                    "order_id": "ORD-1",
                    "status": "Open",
                    "created_at": "2026-05-18T10:00:00Z",
                    "blocker": "Missing POD",
                }
            ]
        }
    )

    first = import_seat_kpi_feed("billing_exceptions", content, filename="billing.json", store=store)
    second = import_seat_kpi_feed("billing_exceptions", content, filename="billing.json", store=store)
    status = get_seat_kpi_feed_status("billing_exceptions", store=store)

    assert first.status == "ok"
    assert first.imported_count == 1
    assert second.duplicate_count == 1
    assert status["status"] == "healthy"
    assert status["row_count"] == 1
    assert status["summary"]["open_count"] == 1


def test_dispatch_timestamp_feed_rejects_rows_without_timestamp() -> None:
    rows, errors = parse_seat_kpi_feed_content(
        "dispatch_timestamps",
        "load_id,status\nLOAD-1,Assigned\n",
        filename="dispatch.csv",
    )

    assert rows == []
    assert errors == ["row 1: missing ready_at"]


def test_weekly_close_dry_run_does_not_write(tmp_path) -> None:
    state_path = tmp_path / "weekly-close.json"
    store = SeatKpiFeedStateStore(FEED_SPECS["weekly_close_variance"], state_path)
    result = import_seat_kpi_feed(
        "weekly_close_variance",
        "week_start,variance_amount,status\n2026-05-18,125.25,Reconciled\n",
        filename="weekly-close.csv",
        dry_run=True,
        store=store,
    )

    assert result.status == "ok"
    assert result.imported_count == 1
    assert not state_path.exists()
