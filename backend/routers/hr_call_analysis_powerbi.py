"""Read-only Power BI exports for HR call-analysis analytics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from services.hr_call_analysis_service import get_department_call_analysis_dataset, get_hr_call_analysis_dataset

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _with_meta(row: dict[str, Any], connection_name: str) -> dict[str, Any]:
    return {
        **row,
        "connection_name": connection_name,
        "exported_at": _now_iso(),
        "source_system": "Grasshopper / Microsoft SharePoint",
        "source_authority": "Grasshopper call logs + SharePoint HR call-analysis reports",
        "projection_mode": "read_only",
    }


def _period(snapshot: dict[str, Any]) -> dict[str, Any]:
    coverage = snapshot.get("coverage") or {}
    return {
        "generated_at": snapshot["generated_at"],
        "source_status": snapshot["source_status"],
        "source_message": snapshot["source_message"],
        "last_imported_at": snapshot.get("last_imported_at"),
        "coverage_start": coverage.get("start"),
        "coverage_end": coverage.get("end"),
        "pii_suppressed": snapshot["pii_suppressed"],
    }


@router.get("/hr-call-analysis/summary")
async def powerbi_hr_call_analysis_summary() -> list[dict[str, Any]]:
    snapshot = await get_hr_call_analysis_dataset()
    return [
        _with_meta(
            {
                **_period(snapshot),
                **snapshot["summary"],
            },
            "hr_call_analysis_summary",
        )
    ]


@router.get("/hr-call-analysis/employees")
async def powerbi_hr_call_analysis_employees() -> list[dict[str, Any]]:
    snapshot = await get_hr_call_analysis_dataset()
    period = _period(snapshot)
    return [
        _with_meta({**period, **row}, "hr_call_analysis_employees")
        for row in snapshot["employee_productivity"]
    ]


@router.get("/hr-call-analysis/monthly-employees")
async def powerbi_hr_call_analysis_monthly_employees() -> list[dict[str, Any]]:
    snapshot = await get_hr_call_analysis_dataset()
    period = _period(snapshot)
    return [
        _with_meta({**period, **row}, "hr_call_analysis_monthly_employees")
        for row in snapshot["monthly_employee_productivity"]
    ]


@router.get("/hr-call-analysis/follow-up")
async def powerbi_hr_call_analysis_follow_up() -> list[dict[str, Any]]:
    snapshot = await get_hr_call_analysis_dataset()
    period = _period(snapshot)
    return [
        _with_meta({**period, **row}, "hr_call_analysis_follow_up")
        for row in snapshot["follow_up"]
    ]


@router.get("/hr-call-analysis/coaching-flags")
async def powerbi_hr_call_analysis_coaching_flags() -> list[dict[str, Any]]:
    snapshot = await get_hr_call_analysis_dataset()
    period = _period(snapshot)
    return [
        _with_meta({**period, **row}, "hr_call_analysis_coaching_flags")
        for row in snapshot["coaching_flags"]
    ]


@router.get("/hr-call-analysis-snapshot")
async def powerbi_hr_call_analysis_snapshot() -> dict[str, Any]:
    snapshot = await get_hr_call_analysis_dataset()
    return {
        "connection_name": "hr_call_analysis_snapshot",
        "exported_at": _now_iso(),
        "source_system": "Grasshopper / Microsoft SharePoint",
        "source_authority": "Grasshopper call logs + SharePoint HR call-analysis reports",
        "projection_mode": "read_only",
        **snapshot,
    }


@router.get("/department-call-analysis/summary")
async def powerbi_department_call_analysis_summary() -> list[dict[str, Any]]:
    snapshot = await get_department_call_analysis_dataset(department="All")
    rows: list[dict[str, Any]] = []
    for rollup in snapshot.get("department_rollups", []):
        rows.append(
            _with_meta(
                {
                    "department": rollup["department"],
                    "department_key": rollup["department_key"],
                    **_period({**snapshot, "coverage": rollup["coverage"]}),
                    **rollup["summary"],
                },
                "department_call_analysis_summary",
            )
        )
    return rows


@router.get("/department-call-analysis/employees")
async def powerbi_department_call_analysis_employees() -> list[dict[str, Any]]:
    snapshot = await get_department_call_analysis_dataset(department="All")
    rows: list[dict[str, Any]] = []
    for rollup in snapshot.get("department_rollups", []):
        for employee in rollup.get("top_employees", []):
            rows.append(_with_meta({**_period(snapshot), **employee}, "department_call_analysis_employees"))
    return rows


@router.get("/department-call-analysis-snapshot")
async def powerbi_department_call_analysis_snapshot() -> dict[str, Any]:
    snapshot = await get_department_call_analysis_dataset(department="All")
    return {
        "connection_name": "department_call_analysis_snapshot",
        "exported_at": _now_iso(),
        "source_system": "Grasshopper / Microsoft SharePoint",
        "source_authority": "Grasshopper call logs + SharePoint department call-analysis reports",
        "projection_mode": "read_only",
        **snapshot,
    }
