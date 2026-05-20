"""Regression tests for local Xcelerator ReviewOrders feed caching."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from integrations.xcelerator.review_orders_feed import (  # noqa: E402
    ReviewOrdersFeedConfig,
    clear_review_orders_feed_cache,
    load_review_orders_rows,
)
from services.xcelerator_review_orders_import_service import (  # noqa: E402
    XceleratorReviewOrdersStateStore,
    clear_xcelerator_review_orders_cache,
    get_xcelerator_review_orders_summary,
)


def test_review_orders_feed_loader_caches_local_json_by_file_signature(monkeypatch, tmp_path):
    path = tmp_path / "review-orders.json"
    path.write_text(
        json.dumps({"rows": [{"OrderTrackingID": "1", "PFrom Date": "2026-01-01"}]}),
        encoding="utf-8",
    )
    clear_review_orders_feed_cache()

    original_read_text = Path.read_text
    read_count = 0

    def spy_read_text(self: Path, *args, **kwargs):
        nonlocal read_count
        if self == path:
            read_count += 1
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy_read_text)

    config = ReviewOrdersFeedConfig(path=str(path))
    assert load_review_orders_rows(config)[0]["OrderTrackingID"] == "1"
    assert load_review_orders_rows(config)[0]["OrderTrackingID"] == "1"
    assert read_count == 1

    path.write_text(
        json.dumps({"rows": [{"OrderTrackingID": "2", "PFrom Date": "2026-01-02"}]}),
        encoding="utf-8",
    )
    assert load_review_orders_rows(config)[0]["OrderTrackingID"] == "2"
    assert read_count == 2


def test_review_orders_state_store_caches_rows_by_file_signature(monkeypatch, tmp_path):
    path = tmp_path / "review-orders-state.json"
    path.write_text(
        json.dumps({"rows": [{"OrderTrackingID": "1", "PFrom Date": "2026-01-01"}]}),
        encoding="utf-8",
    )
    clear_xcelerator_review_orders_cache()

    original_read_text = Path.read_text
    read_count = 0

    def spy_read_text(self: Path, *args, **kwargs):
        nonlocal read_count
        if self == path:
            read_count += 1
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy_read_text)

    store = XceleratorReviewOrdersStateStore(path=path)
    assert store.rows()[0]["OrderTrackingID"] == "1"
    assert store.rows()[0]["OrderTrackingID"] == "1"
    assert read_count == 1

    path.write_text(
        json.dumps({"rows": [{"OrderTrackingID": "2", "PFrom Date": "2026-01-02"}]}),
        encoding="utf-8",
    )
    assert store.rows()[0]["OrderTrackingID"] == "2"
    assert read_count == 2


def test_review_orders_summary_fails_fast_when_state_file_is_too_large(monkeypatch, tmp_path):
    path = tmp_path / "review-orders-state.json"
    path.write_text(
        json.dumps({"rows": [{"OrderTrackingID": "1", "PFrom Date": "2026-01-01"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("FLEETPULSE_XCELERATOR_REVIEW_ORDERS_MAX_SYNC_STATE_BYTES", "1")
    clear_xcelerator_review_orders_cache()

    summary = get_xcelerator_review_orders_summary(
        store=XceleratorReviewOrdersStateStore(path=path),
    )

    assert summary["status"] == "unavailable"
    assert summary["state_size_bytes"] > summary["max_sync_state_bytes"]
    assert summary["row_count"] == 0
