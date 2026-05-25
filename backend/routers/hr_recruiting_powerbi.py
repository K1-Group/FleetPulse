"""Read-only Power BI exports for HR recruiting worklist analytics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from services.hr_recruiting_service import get_hr_recruiting_dataset

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _with_hr_recruiting_meta(
    row: dict[str, Any],
    connection_name: str,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    return {
        **row,
        "connection_name": connection_name,
        "exported_at": _now_iso(),
        "source_system": snapshot.get("source_system"),
        "source_authority": snapshot.get("source_authority"),
        "source_profile": snapshot.get("source_profile"),
        "projection_mode": "read_only",
    }


def _hr_period(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": snapshot["generated_at"],
        "source": snapshot["source"],
        "source_profile": snapshot.get("source_profile"),
        "source_artifact": snapshot.get("source_artifact"),
        "table_id": snapshot["table_id"],
        "source_status": snapshot["source_status"],
        "source_message": snapshot["source_message"],
        "pii_suppressed": snapshot["pii_suppressed"],
        "sla_hours": ",".join(str(value) for value in snapshot.get("sla_hours", [])),
    }


@router.get("/hr-recruiting/summary")
async def powerbi_hr_recruiting_summary() -> list[dict[str, Any]]:
    """Power BI HR recruiting table: one-row worklist KPI summary."""
    snapshot = await get_hr_recruiting_dataset()
    return [
        _with_hr_recruiting_meta(
            {
                **_hr_period(snapshot),
                **snapshot["summary"],
                "hard_target_status": snapshot.get("hard_target_status"),
                "hard_target_misses": ",".join(snapshot.get("hard_target_misses", [])),
                "hard_target_pending": ",".join(snapshot.get("hard_target_pending", [])),
            },
            "hr_recruiting_summary",
            snapshot,
        )
    ]


@router.get("/hr-recruiting/by-worklist")
async def powerbi_hr_recruiting_by_worklist() -> list[dict[str, Any]]:
    """Power BI HR recruiting table: active/stale lead counts by worklist."""
    snapshot = await get_hr_recruiting_dataset()
    period = _hr_period(snapshot)
    return [
        _with_hr_recruiting_meta({**period, **row}, "hr_recruiting_by_worklist", snapshot)
        for row in snapshot["by_worklist"]
    ]


@router.get("/hr-recruiting/daily")
async def powerbi_hr_recruiting_daily() -> list[dict[str, Any]]:
    """Power BI HR recruiting table: daily worklist volume and completion trend."""
    snapshot = await get_hr_recruiting_dataset()
    period = _hr_period(snapshot)
    return [
        _with_hr_recruiting_meta({**period, **row}, "hr_recruiting_daily", snapshot)
        for row in snapshot["daily"]
    ]


@router.get("/hr-recruiting/status-counts")
async def powerbi_hr_recruiting_status_counts() -> list[dict[str, Any]]:
    """Power BI HR recruiting table: applicant status counts with no PII."""
    snapshot = await get_hr_recruiting_dataset()
    period = _hr_period(snapshot)
    return [
        _with_hr_recruiting_meta({**period, **row}, "hr_recruiting_status_counts", snapshot)
        for row in snapshot["status_counts"]
    ]


@router.get("/hr-recruiting/trend")
async def powerbi_hr_recruiting_trend() -> list[dict[str, Any]]:
    """Power BI HR recruiting table: active, new, stale, and age trend."""
    snapshot = await get_hr_recruiting_dataset()
    period = _hr_period(snapshot)
    return [
        _with_hr_recruiting_meta({**period, **row}, "hr_recruiting_trend", snapshot)
        for row in snapshot["trend"]
    ]


@router.get("/hr-recruiting-snapshot")
async def powerbi_hr_recruiting_snapshot() -> dict[str, Any]:
    """Power BI HR recruiting snapshot for one-source imports."""
    snapshot = await get_hr_recruiting_dataset()
    return {
        "connection_name": "hr_recruiting_snapshot",
        "exported_at": _now_iso(),
        "source_system": snapshot.get("source_system"),
        "source_authority": snapshot.get("source_authority"),
        "source_profile": snapshot.get("source_profile"),
        "projection_mode": "read_only",
        **snapshot,
    }
