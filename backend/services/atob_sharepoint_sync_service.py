"""Sync AtoB fuel report files from a BI-connected SharePoint folder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from configs.atob_fuel import AtoBSharePointConfig
from integrations.sharepoint.graph_drive_client import SharePointDriveClient, SharePointDriveFile
from services.atob_fuel_expense_service import (
    AtoBFuelExpenseStateStore,
    import_atob_fuel_expenses,
)

ATOB_SHAREPOINT_SOURCE_AUTHORITY = "SharePoint / AtoB fuel folder"


class AtoBSharePointConfigError(RuntimeError):
    """Raised when SharePoint AtoB sync is called without required config."""


@dataclass(frozen=True)
class AtoBSharePointFileSyncResult:
    filename: str
    web_url: str | None
    last_modified_at: str | None
    imported_count: int
    duplicate_count: int
    invalid_count: int
    errors: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "web_url": self.web_url,
            "last_modified_at": self.last_modified_at,
            "imported_count": self.imported_count,
            "duplicate_count": self.duplicate_count,
            "invalid_count": self.invalid_count,
            "errors": self.errors,
        }


@dataclass(frozen=True)
class AtoBSharePointSyncResult:
    status: str
    dry_run: bool
    folder_path: str
    fetched_count: int
    imported_count: int
    duplicate_count: int
    invalid_count: int
    errors: list[str]
    files: list[AtoBSharePointFileSyncResult]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_authority": ATOB_SHAREPOINT_SOURCE_AUTHORITY,
            "projection_mode": "read_only",
            "dry_run": self.dry_run,
            "folder_path": self.folder_path,
            "fetched_count": self.fetched_count,
            "imported_count": self.imported_count,
            "duplicate_count": self.duplicate_count,
            "invalid_count": self.invalid_count,
            "errors": self.errors,
            "files": [file.as_dict() for file in self.files],
        }


def atob_sharepoint_status(
    config: AtoBSharePointConfig | None = None,
) -> dict[str, Any]:
    config = config or AtoBSharePointConfig.from_env()
    return {
        "enabled": config.enabled,
        "sync_ready": config.sync_ready,
        "source_authority": ATOB_SHAREPOINT_SOURCE_AUTHORITY,
        "projection_mode": "read_only",
        "site_configured": config.site_configured,
        "drive_configured": bool(config.drive_id or config.drive_name),
        "folder_path": config.folder_path,
        "source_file_url_count": len(config.source_file_urls),
        "file_extensions": list(config.file_extensions),
        "file_limit": config.file_limit,
        "api_key_required": config.api_key_required,
        "missing_config": config.missing_sync_config(),
        "powerbi_connection": {
            "workspace_id": config.powerbi_workspace_id or None,
            "folder_id": config.powerbi_folder_id or None,
            "ui_subfolder_id": config.powerbi_ui_subfolder_id or None,
            "report_id": config.powerbi_report_id or None,
            "semantic_model_id": config.powerbi_semantic_model_id or None,
        },
    }


def validate_sharepoint_sync_api_key(
    config: AtoBSharePointConfig,
    supplied_key: str | None,
) -> None:
    if config.sync_api_key and supplied_key != config.sync_api_key:
        raise PermissionError("invalid_atob_sharepoint_ingestion_key")


def sync_atob_sharepoint_folder(
    config: AtoBSharePointConfig | None = None,
    *,
    client: SharePointDriveClient | None = None,
    dry_run: bool = False,
    store: AtoBFuelExpenseStateStore | None = None,
) -> AtoBSharePointSyncResult:
    config = config or AtoBSharePointConfig.from_env()
    if not config.sync_ready:
        missing = ",".join(config.missing_sync_config())
        raise AtoBSharePointConfigError(f"atob_sharepoint_sync_not_configured:{missing}")

    graph_client = client or SharePointDriveClient(config)
    files = graph_client.list_files()
    store = store or AtoBFuelExpenseStateStore()

    file_results: list[AtoBSharePointFileSyncResult] = []
    errors: list[str] = []
    imported_count = 0
    duplicate_count = 0
    invalid_count = 0

    for file in files:
        try:
            file_result = _sync_file(
                graph_client,
                file,
                folder_path=config.folder_path,
                dry_run=dry_run,
                store=store,
            )
        except Exception as exc:
            message = f"{file.name}: {type(exc).__name__}"
            file_result = AtoBSharePointFileSyncResult(
                filename=file.name,
                web_url=file.web_url,
                last_modified_at=(
                    file.last_modified_at.isoformat()
                    if file.last_modified_at
                    else None
                ),
                imported_count=0,
                duplicate_count=0,
                invalid_count=1,
                errors=[message],
            )
        file_results.append(file_result)
        imported_count += file_result.imported_count
        duplicate_count += file_result.duplicate_count
        invalid_count += file_result.invalid_count
        errors.extend(file_result.errors)

    status = "ok" if not errors else "partial"
    return AtoBSharePointSyncResult(
        status=status,
        dry_run=dry_run,
        folder_path=config.folder_path,
        fetched_count=len(files),
        imported_count=imported_count,
        duplicate_count=duplicate_count,
        invalid_count=invalid_count,
        errors=errors,
        files=file_results,
    )


def _sync_file(
    client: SharePointDriveClient,
    file: SharePointDriveFile,
    *,
    folder_path: str,
    dry_run: bool,
    store: AtoBFuelExpenseStateStore,
) -> AtoBSharePointFileSyncResult:
    content = client.download_file_text(file)
    filename = f"sharepoint/{folder_path}/{file.name}" if folder_path else f"sharepoint/{file.name}"
    import_result = import_atob_fuel_expenses(
        content,
        filename=filename,
        dry_run=dry_run,
        store=store,
    )
    return AtoBSharePointFileSyncResult(
        filename=file.name,
        web_url=file.web_url,
        last_modified_at=file.last_modified_at.isoformat() if file.last_modified_at else None,
        imported_count=import_result.imported_count,
        duplicate_count=import_result.duplicate_count,
        invalid_count=import_result.invalid_count,
        errors=import_result.errors,
    )
