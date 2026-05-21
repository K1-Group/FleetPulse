"""Tests for syncing AtoB fuel reports from SharePoint."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from configs.atob_fuel import AtoBSharePointConfig  # noqa: E402
from integrations.sharepoint.graph_drive_client import SharePointDriveFile  # noqa: E402
from services.atob_fuel_expense_service import AtoBFuelExpenseStateStore  # noqa: E402
from services.atob_sharepoint_sync_service import (  # noqa: E402
    atob_sharepoint_status,
    sync_atob_sharepoint_folder,
)


class FakeSharePointClient:
    def __init__(self, files: dict[str, str]):
        self._files = files

    def list_files(self) -> list[SharePointDriveFile]:
        return [
            SharePointDriveFile(
                id=name,
                name=name,
                web_url=f"https://sharepoint.example/{name}",
                last_modified_at=datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc),
                size=len(content),
                e_tag=f"etag-{name}",
            )
            for name, content in self._files.items()
        ]

    def download_file_text(self, file: SharePointDriveFile) -> str:
        return self._files[file.name]


def _config() -> AtoBSharePointConfig:
    return AtoBSharePointConfig(
        enabled=True,
        graph_tenant_id="tenant",
        graph_client_id="client",
        graph_client_secret="secret",
        site_id="site",
        site_url="",
        site_hostname="",
        site_path="",
        drive_id="drive",
        drive_name="",
        folder_path="fuel/atob",
        source_file_urls=(),
        file_extensions=(".csv",),
        file_limit=25,
        sync_api_key="",
        timeout_seconds=20,
        retry_count=0,
        retry_backoff_seconds=0,
        powerbi_workspace_id="",
        powerbi_folder_id="",
        powerbi_ui_subfolder_id="",
        powerbi_report_id="",
        powerbi_semantic_model_id="",
    )


def _sample_csv(transaction_id: str) -> str:
    return (
        "Transaction ID,Transaction Date,Merchant,Amount,Gallons,Vehicle\n"
        f"{transaction_id},2026-05-14,Pilot,125.00,25.0,5439 Idealease -HDS DFW\n"
    )


def test_sharepoint_sync_imports_and_dedupes_rows(tmp_path):
    store = AtoBFuelExpenseStateStore(tmp_path / "atob-state.json")
    client = FakeSharePointClient({"atob-export.csv": _sample_csv("SP-100")})

    first = sync_atob_sharepoint_folder(_config(), client=client, store=store)
    second = sync_atob_sharepoint_folder(_config(), client=client, store=store)

    assert first.imported_count == 1
    assert first.duplicate_count == 0
    assert first.files[0].filename == "atob-export.csv"
    assert second.imported_count == 0
    assert second.duplicate_count == 1


def test_sharepoint_status_reports_missing_configuration():
    config = AtoBSharePointConfig(
        enabled=False,
        graph_tenant_id="",
        graph_client_id="",
        graph_client_secret="",
        site_id="",
        site_url="",
        site_hostname="",
        site_path="",
        drive_id="",
        drive_name="",
        folder_path="atob",
        source_file_urls=(),
        file_extensions=(".csv",),
        file_limit=25,
        sync_api_key="expected",
        timeout_seconds=20,
        retry_count=0,
        retry_backoff_seconds=0,
        powerbi_workspace_id="",
        powerbi_folder_id="",
        powerbi_ui_subfolder_id="",
        powerbi_report_id="",
        powerbi_semantic_model_id="",
    )

    status = atob_sharepoint_status(config)

    assert status["sync_ready"] is False
    assert status["api_key_required"] is True
    assert "FLEETPULSE_GRAPH_TENANT_ID" in status["missing_config"]
    assert status["power_automate_flow"]["status"] == "validated_success"
    assert status["power_automate_flow"]["flow_id"] == "34873590-059e-4317-9e1b-4dfc603e5653"
    assert status["power_automate_flow"]["latest_run_id"] == "08584221997564109507812261464CU09"
    assert "HTTP - Follow Redirect 2" in status["power_automate_flow"]["validation_path"]
    assert status["loading_optimization_plan"][0]["status"] == "in_progress"


def test_sharepoint_status_accepts_powerbi_source_file_url_without_site():
    config = AtoBSharePointConfig(
        enabled=True,
        graph_tenant_id="tenant",
        graph_client_id="client",
        graph_client_secret="secret",
        site_id="",
        site_url="",
        site_hostname="",
        site_path="",
        drive_id="",
        drive_name="",
        folder_path="",
        source_file_urls=("https://tenant.sharepoint.com/sites/k1/Shared Documents/atob.csv",),
        file_extensions=(".csv",),
        file_limit=25,
        sync_api_key="",
        timeout_seconds=20,
        retry_count=0,
        retry_backoff_seconds=0,
        powerbi_workspace_id="workspace",
        powerbi_folder_id="folder",
        powerbi_ui_subfolder_id="52730",
        powerbi_report_id="report",
        powerbi_semantic_model_id="model",
    )

    status = atob_sharepoint_status(config)

    assert status["sync_ready"] is True
    assert status["source_file_url_count"] == 1
    assert status["powerbi_connection"]["semantic_model_id"] == "model"
    assert "sharepoint.com" not in str(status)
