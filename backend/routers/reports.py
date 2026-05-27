"""PDF Fleet Report generation endpoints."""

from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from geotab_client import GeotabClient
from _cache import get_cached, set_cached
from services.trailer_tracking_service import get_live_trailer_tracking
from services.fleet_report_delivery_service import (
    get_due_report_schedule_status,
    get_report_schedule_status,
    record_report_schedule_attempt,
    save_report_schedule,
    send_report_email,
)

router = APIRouter()


class ReportEmailRequest(BaseModel):
    recipients: list[str] = Field(default_factory=list)
    subject: str | None = None
    message: str | None = None
    period: str = "weekly"
    html: str
    summary: dict[str, Any] = Field(default_factory=dict)
    generated_at: str | None = None


class ReportScheduleRequest(BaseModel):
    enabled: bool = False
    period: str = "weekly"
    frequency: str = "weekly"
    recipients: list[str] = Field(default_factory=list)
    send_time: str = "07:00"
    timezone: str = "America/Chicago"
    weekday: int | None = None
    day_of_month: int | None = None


class ScheduledReportRunRequest(BaseModel):
    force: bool = False
    now: str | None = None


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _report_cache_ttl_seconds() -> int:
    return max(60, _int_env("FLEETPULSE_REPORT_CACHE_SECONDS", 900))


def _report_stale_ttl_seconds() -> int:
    return max(_report_cache_ttl_seconds(), _int_env("FLEETPULSE_REPORT_STALE_CACHE_SECONDS", 86400))


def _is_source_quota_error(exc: Exception) -> bool:
    message = str(exc)
    return "OverLimitException" in message or "API calls quota exceeded" in message


def _build_html_report(
    fleet_data: dict[str, Any],
    period: str,
    *,
    period_start: datetime,
    period_end: datetime,
) -> str:
    """Build an HTML fleet report that can be rendered as PDF on the frontend."""
    now = datetime.now(timezone.utc)
    
    devices = fleet_data.get("devices", [])
    trips = fleet_data.get("trips", [])
    exceptions = fleet_data.get("exceptions", [])
    trailer_tracking = fleet_data.get("trailer_tracking")
    trailer_summary = getattr(trailer_tracking, "summary", None)
    trailers = getattr(trailer_tracking, "trailers", []) if trailer_tracking else []
    
    total_vehicles = len(devices)
    total_trips = len(trips)
    
    # Calculate total distance
    total_distance_km = sum(
        (t.get("distance", 0) or 0) for t in trips
    )
    total_distance_mi = total_distance_km * 0.621371
    
    # Exception breakdown
    exception_counts: dict[str, int] = {}
    for ex in exceptions:
        rule = ex.get("rule", {})
        name = rule.get("name", "Unknown") if isinstance(rule, dict) else str(rule)
        exception_counts[name] = exception_counts.get(name, 0) + 1
    
    top_exceptions = sorted(exception_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # Vehicle utilization
    active_device_ids = set()
    for t in trips:
        dev = t.get("device", {})
        if isinstance(dev, dict):
            active_device_ids.add(dev.get("id", ""))
    
    utilization_pct = (len(active_device_ids) / total_vehicles * 100) if total_vehicles else 0
    
    # Build vehicle summary rows
    vehicle_rows = ""
    device_trip_counts: dict[str, dict] = {}
    for t in trips:
        dev = t.get("device", {})
        dev_id = dev.get("id", "") if isinstance(dev, dict) else ""
        if dev_id not in device_trip_counts:
            device_trip_counts[dev_id] = {"trips": 0, "distance": 0}
        device_trip_counts[dev_id]["trips"] += 1
        device_trip_counts[dev_id]["distance"] += (t.get("distance", 0) or 0)
    
    for d in devices[:20]:  # Top 20 vehicles
        d_id = d.get("id", "")
        d_name = d.get("name", "Unknown")
        stats = device_trip_counts.get(d_id, {"trips": 0, "distance": 0})
        dist_mi = stats["distance"] * 0.621371
        vehicle_rows += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #e5e7eb">{d_name}</td>
            <td style="padding:8px;border-bottom:1px solid #e5e7eb;text-align:center">{stats['trips']}</td>
            <td style="padding:8px;border-bottom:1px solid #e5e7eb;text-align:right">{dist_mi:,.0f} mi</td>
        </tr>"""
    
    exception_rows = ""
    for name, count in top_exceptions:
        exception_rows += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #e5e7eb">{name}</td>
            <td style="padding:8px;border-bottom:1px solid #e5e7eb;text-align:center">{count}</td>
        </tr>"""

    trailer_rows = ""
    for trailer in trailers[:30]:
        custody = trailer.custody
        event = trailer.xtra_last_event
        custody_label = custody.vehicle_name or "Unassigned"
        if custody.driver_name:
            custody_label = f"{custody_label} / {custody.driver_name}"
        gps_status = getattr(trailer.gps_status, "value", str(trailer.gps_status))
        trailer_rows += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #e5e7eb">{escape(trailer.trailer_id)}</td>
            <td style="padding:8px;border-bottom:1px solid #e5e7eb">{escape(gps_status)}</td>
            <td style="padding:8px;border-bottom:1px solid #e5e7eb">{escape(event.event_type if event else 'No XTRA event')}</td>
            <td style="padding:8px;border-bottom:1px solid #e5e7eb">{escape(custody_label)}</td>
            <td style="padding:8px;border-bottom:1px solid #e5e7eb;text-align:right">{escape(custody.confidence)}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>FleetPulse Report - {period}</title>
<style>
    body {{ font-family: 'Segoe UI', Tahoma, sans-serif; color: #1f2937; margin: 0; padding: 40px; background: white; }}
    .header {{ background: linear-gradient(135deg, #1e40af, #7c3aed); color: white; padding: 30px; border-radius: 12px; margin-bottom: 30px; }}
    .header h1 {{ margin: 0; font-size: 28px; }}
    .header p {{ margin: 5px 0 0; opacity: 0.8; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 30px; }}
    .kpi-card {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; text-align: center; }}
    .kpi-value {{ font-size: 32px; font-weight: bold; color: #1e40af; }}
    .kpi-label {{ font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 4px; }}
    .section {{ margin-bottom: 30px; }}
    .section h2 {{ font-size: 18px; color: #1f2937; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ background: #f3f4f6; padding: 10px 8px; text-align: left; font-size: 12px; text-transform: uppercase; color: #6b7280; }}
    .footer {{ text-align: center; color: #9ca3af; font-size: 11px; margin-top: 40px; padding-top: 20px; border-top: 1px solid #e5e7eb; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }}
    .badge-green {{ background: #d1fae5; color: #065f46; }}
    .badge-yellow {{ background: #fef3c7; color: #92400e; }}
    .badge-red {{ background: #fee2e2; color: #991b1b; }}
    @media print {{ body {{ padding: 20px; }} .header {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }} }}
</style>
</head>
<body>
    <div class="header">
        <h1>🚗 FleetPulse Report</h1>
        <p>K1 Logistics · {period} Report</p>
        <p>Window: {period_start.strftime('%B %d, %Y %I:%M %p UTC')} – {period_end.strftime('%B %d, %Y %I:%M %p UTC')}</p>
        <p>Generated: {now.strftime('%B %d, %Y at %I:%M %p UTC')}</p>
    </div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-value">{total_vehicles}</div>
            <div class="kpi-label">Total Vehicles</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-value">{total_trips}</div>
            <div class="kpi-label">Total Trips</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-value">{total_distance_mi:,.0f}</div>
            <div class="kpi-label">Miles Driven</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-value">{utilization_pct:.0f}%</div>
            <div class="kpi-label">Fleet Utilization</div>
        </div>
    </div>

    <div class="section">
        <h2>📊 Vehicle Activity Summary</h2>
        <table>
            <thead>
                <tr>
                    <th>Vehicle</th>
                    <th style="text-align:center">Trips</th>
                    <th style="text-align:right">Distance</th>
                </tr>
            </thead>
            <tbody>{vehicle_rows if vehicle_rows else '<tr><td colspan="3" style="padding:20px;text-align:center;color:#9ca3af">No trip data for this period</td></tr>'}</tbody>
        </table>
    </div>

    <div class="section">
        <h2>Trailer Custody Snapshot</h2>
        <p>
            Live trailer tracking shows <strong>{getattr(trailer_summary, 'gps_active', 0)}</strong> trailers with current Geotab GPS,
            <strong>{getattr(trailer_summary, 'xtra_event_trailers', 0)}</strong> trailers with recent XTRA geofence events, and
            <strong>{getattr(trailer_summary, 'custody_inferred', 0)}</strong> proximity-based custody matches.
        </p>
        <table>
            <thead>
                <tr>
                    <th>Trailer</th>
                    <th>GPS</th>
                    <th>Last XTRA Event</th>
                    <th>Candidate Tractor / Driver</th>
                    <th style="text-align:right">Confidence</th>
                </tr>
            </thead>
            <tbody>{trailer_rows if trailer_rows else '<tr><td colspan="5" style="padding:20px;text-align:center;color:#9ca3af">No live trailer tracking data available</td></tr>'}</tbody>
        </table>
    </div>

    <div class="section">
        <h2>⚠️ Safety Exception Summary</h2>
        <table>
            <thead>
                <tr>
                    <th>Exception Type</th>
                    <th style="text-align:center">Count</th>
                </tr>
            </thead>
            <tbody>{exception_rows if exception_rows else '<tr><td colspan="2" style="padding:20px;text-align:center;color:#9ca3af">No exceptions for this period</td></tr>'}</tbody>
        </table>
    </div>

    <div class="section">
        <h2>📈 Fleet Health Overview</h2>
        <p>During this {period.lower()} period, the fleet maintained a <span class="badge {'badge-green' if utilization_pct > 70 else 'badge-yellow' if utilization_pct > 40 else 'badge-red'}">{utilization_pct:.0f}% utilization rate</span>.</p>
        <p>A total of <strong>{len(exceptions)}</strong> safety exceptions were recorded across <strong>{total_trips}</strong> trips, 
        resulting in an exception rate of <strong>{(len(exceptions)/max(total_trips,1)*100):.1f}%</strong> per trip.</p>
    </div>

    <div class="footer">
        <p>FleetPulse · Powered by Geotab · Budget Rent a Car Las Vegas</p>
        <p>This report was auto-generated. For questions, contact fleet operations.</p>
    </div>
</body>
</html>"""
    return html


def _build_error_report(period: str, error: Exception) -> dict[str, Any]:
    status = "source_quota_limited" if _is_source_quota_error(error) else "source_unavailable"
    safe_error = escape(str(error))
    now = datetime.now(timezone.utc)
    return {
        "html": f"<h1>Report Generation Error</h1><p>{safe_error}</p>",
        "period": period,
        "period_start": None,
        "period_end": now.isoformat(),
        "generated_at": now.isoformat(),
        "summary": {},
        "source_status": status,
        "error": str(error),
    }


def _generate_report_payload(period: str = "weekly") -> dict[str, Any]:
    """Generate a source-backed fleet report payload."""
    period = str(period or "weekly").lower()
    if period not in {"daily", "weekly", "monthly"}:
        raise ValueError("Report period must be daily, weekly, or monthly.")

    cache_key = f"report:{period}"
    cached = get_cached(cache_key, ttl=_report_cache_ttl_seconds())
    if cached:
        return cached

    try:
        client = GeotabClient.get()
        now = datetime.now(timezone.utc)

        if period == "daily":
            from_date = now - timedelta(days=1)
        elif period == "monthly":
            from_date = now - timedelta(days=30)
        else:  # weekly
            from_date = now - timedelta(days=7)

        devices = client.get_devices()
        trips = client.get_trips(from_date=from_date, to_date=now)
        exceptions = client.get_exception_events(from_date=from_date, to_date=now)
        source_warnings: list[str] = []
        try:
            trailer_tracking = get_live_trailer_tracking()
        except Exception as exc:
            trailer_tracking = None
            source_warnings.append(f"Trailer tracking unavailable: {type(exc).__name__}")

        fleet_data = {
            "devices": devices,
            "trips": trips,
            "exceptions": exceptions,
            "trailer_tracking": trailer_tracking,
        }

        html = _build_html_report(
            fleet_data,
            period.capitalize(),
            period_start=from_date,
            period_end=now,
        )

        result = {
            "html": html,
            "period": period,
            "period_start": from_date.isoformat(),
            "period_end": now.isoformat(),
            "generated_at": now.isoformat(),
            "source_status": "source_backed" if not source_warnings else "partial_source_backed",
            "source_warnings": source_warnings,
            "summary": {
                "total_vehicles": len(devices),
                "total_trips": len(trips),
                "total_exceptions": len(exceptions),
                "total_distance_mi": sum((t.get("distance", 0) or 0) for t in trips) * 0.621371,
                "trailers_tracked": trailer_tracking.summary.total_trailers if trailer_tracking else 0,
                "trailer_custody_inferred": trailer_tracking.summary.custody_inferred if trailer_tracking else 0,
            }
        }

        set_cached(cache_key, result, ttl=_report_cache_ttl_seconds())
        return result

    except Exception as e:
        stale = get_cached(cache_key, ttl=_report_stale_ttl_seconds())
        if stale:
            result = dict(stale)
            warnings = list(result.get("source_warnings") or [])
            warnings.append(f"Current Geotab report refresh failed: {type(e).__name__}")
            result["source_status"] = "stale_source_cache"
            result["source_warnings"] = warnings
            result["error"] = str(e)
            return result
        return _build_error_report(period, e)


@router.get("/generate")
async def generate_report(period: str = "weekly"):
    """Generate fleet report data as HTML (rendered to PDF on frontend via print)."""
    try:
        return _generate_report_payload(period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/email")
async def email_report(request: ReportEmailRequest):
    """Send a generated report through the configured delivery webhook."""
    try:
        return send_report_email(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/schedule")
async def get_report_schedule():
    """Return saved report schedule settings and delivery readiness."""
    return get_report_schedule_status()


@router.post("/schedule")
async def update_report_schedule(request: ReportScheduleRequest):
    """Persist report schedule settings for the external scheduler/orchestrator."""
    try:
        return save_report_schedule(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/schedule/run")
async def run_scheduled_report(request: ScheduledReportRunRequest | None = None):
    """Run the saved scheduled report when an external scheduler calls at the due time."""
    run_request = request or ScheduledReportRunRequest()
    due_status = get_due_report_schedule_status(run_request.now)
    if not due_status.get("due") and not run_request.force:
        return {"status": "skipped", **due_status}

    schedule = due_status["schedule"]
    run_key = due_status.get("run_key") or f"manual:{datetime.now(timezone.utc).isoformat()}"
    scheduled_for = due_status.get("scheduled_for") or datetime.now(timezone.utc).isoformat()

    if not due_status.get("delivery_ready"):
        message = "FLEETPULSE_REPORT_EMAIL_WEBHOOK_URL is required for scheduled report delivery."
        schedule_status = record_report_schedule_attempt(
            message=message,
            run_key=run_key,
            scheduled_for=scheduled_for,
            status="needs_configuration",
        )
        return {
            "status": "needs_configuration",
            "message": message,
            "run_key": run_key,
            "scheduled_for": scheduled_for,
            **schedule_status,
        }

    report = _generate_report_payload(schedule.get("period", "weekly"))
    if report.get("error") and not report.get("summary"):
        record_report_schedule_attempt(
            message=str(report["error"]),
            run_key=run_key,
            scheduled_for=scheduled_for,
            status="failed",
        )
        raise HTTPException(status_code=503, detail=str(report["error"]))

    try:
        delivery_result = send_report_email(
            {
                "recipients": schedule.get("recipients") or [],
                "period": schedule.get("period") or "weekly",
                "subject": f"FleetPulse {str(schedule.get('period') or 'weekly').capitalize()} Report",
                "html": report["html"],
                "summary": report.get("summary") or {},
                "generated_at": scheduled_for,
            }
        )
    except ValueError as exc:
        record_report_schedule_attempt(
            message=str(exc),
            run_key=run_key,
            scheduled_for=scheduled_for,
            status="failed",
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    schedule_status = record_report_schedule_attempt(
        message=delivery_result.get("message", delivery_result.get("status", "")),
        run_key=run_key,
        scheduled_for=scheduled_for,
        status=delivery_result.get("status", "failed"),
    )

    return {
        "status": delivery_result.get("status"),
        "delivery": delivery_result,
        "report": {
            "generated_at": report.get("generated_at"),
            "period": report.get("period"),
            "period_start": report.get("period_start"),
            "period_end": report.get("period_end"),
            "source_status": report.get("source_status"),
            "source_warnings": report.get("source_warnings", []),
            "summary": report.get("summary", {}),
        },
        "run_key": run_key,
        "scheduled_for": scheduled_for,
        **schedule_status,
    }
