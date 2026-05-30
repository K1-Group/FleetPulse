from __future__ import annotations

from datetime import datetime, timezone

from configs.driver_compliance import DriverComplianceConfig
from services.driver_compliance_service import build_driver_compliance_dataset


def _now() -> datetime:
    return datetime(2026, 5, 30, 18, tzinfo=timezone.utc)


def test_driver_compliance_pending_config_is_pipeline_only():
    dataset = build_driver_compliance_dataset(
        [],
        config=DriverComplianceConfig(),
        now=_now(),
    )

    assert dataset["projection_mode"] == "read_only"
    assert dataset["summary"]["drivers"] == 0
    assert [item["key"] for item in dataset["document_types"]] == ["medical_card", "drug_test", "mvr"]
    assert dataset["validation"]["status"] == "pending"
    assert "FLEETPULSE_DRIVER_COMPLIANCE_SOURCE_PATH" in dataset["validation"]["required_config"][0]


def test_driver_compliance_flags_expiring_and_expired_documents():
    rows = [
        {
            "driver_id": "D1",
            "driver_name": "Driver Valid",
            "medical_card_expires": "2026-08-01",
            "drug_test_expires": "2026-07-30",
            "mvr_expires": "2026-09-01",
        },
        {
            "driver_id": "D2",
            "driver_name": "Driver Warning",
            "medical_card_expires": "2026-06-10",
            "drug_test_expires": "2026-05-01",
            "mvr_expires": "",
        },
    ]

    dataset = build_driver_compliance_dataset(
        rows,
        config=DriverComplianceConfig(warning_days=45),
        now=_now(),
        source_status={"status": "healthy", "message": "Loaded test register.", "required_config": [], "row_count": 2},
    )

    assert dataset["validation"]["status"] == "verified"
    assert dataset["summary"]["drivers"] == 2
    assert dataset["summary"]["warning"] == 0
    assert dataset["summary"]["expired"] == 1
    assert dataset["drivers"][0]["driver_name"] == "Driver Warning"
    assert dataset["drivers"][0]["documents"]["drug_test"]["status"] == "expired"
    assert dataset["drivers"][0]["documents"]["medical_card"]["status"] == "warning"
    assert dataset["drivers"][0]["documents"]["mvr"]["status"] == "missing"
