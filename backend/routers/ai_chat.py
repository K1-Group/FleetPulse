"""AI Chat Router - Intelligent fleet query processing."""

from __future__ import annotations

import os
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Literal

import anthropic
import openai
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

router = APIRouter()

# Provider type definition
ProviderType = Literal["anthropic", "openrouter", "demo"]
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-sonnet-4"

# In-memory storage for API configurations (not persisted to disk for security)
_ai_config = {
    "provider": "demo",
    "api_key": None,
    "client": None
}


def _get_anthropic_model() -> str:
    """Return the configured Anthropic model."""
    configured = os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL).strip()
    return configured or DEFAULT_ANTHROPIC_MODEL


def _get_openrouter_model() -> str:
    """Return the configured OpenRouter model."""
    configured = os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL).strip()
    return configured or DEFAULT_OPENROUTER_MODEL


def _get_openrouter_headers() -> dict[str, str] | None:
    """Return optional OpenRouter attribution headers."""
    headers = {}
    site_url = os.getenv("OPENROUTER_SITE_URL", "").strip()
    app_name = os.getenv("OPENROUTER_APP_NAME", "").strip()
    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-Title"] = app_name
    return headers or None


def _build_openrouter_client(api_key: str) -> openai.OpenAI:
    """Build an OpenRouter client with optional attribution headers."""
    kwargs: dict[str, Any] = {
        "api_key": api_key,
        "base_url": "https://openrouter.ai/api/v1",
    }
    headers = _get_openrouter_headers()
    if headers:
        kwargs["default_headers"] = headers
    return openai.OpenAI(**kwargs)

def _set_api_key(api_key: str, provider: ProviderType) -> bool:
    """Set API key and provider in memory and initialize client."""
    global _ai_config
    
    try:
        if provider == "anthropic":
            # Test Anthropic API key
            test_client = anthropic.Anthropic(api_key=api_key)
            test_response = test_client.messages.create(
                model=_get_anthropic_model(),
                max_tokens=10,
                messages=[{"role": "user", "content": "Test"}]
            )
            
            _ai_config = {
                "provider": "anthropic",
                "api_key": api_key,
                "client": test_client
            }
            return True
            
        elif provider == "openrouter":
            # Test OpenRouter API key
            test_client = _build_openrouter_client(api_key)
            
            # Test with a minimal request
            test_response = test_client.chat.completions.create(
                model=_get_openrouter_model(),
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=10
            )
            
            _ai_config = {
                "provider": "openrouter", 
                "api_key": api_key,
                "client": test_client
            }
            return True
            
        else:
            return False
        
    except Exception as e:
        status_code = getattr(e, "status_code", None)
        status_text = f" status={status_code}" if status_code else ""
        print(f"API key validation failed for {provider}: {type(e).__name__}{status_text}")
        return False


# Initialize from environment variables if available
def _initialize_from_env():
    """Initialize AI client from environment variables."""
    global _ai_config

    if _is_ai_enabled():
        return

    # Check for Anthropic API key
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_key and anthropic_key != "your-key-here":
        success = _set_api_key(anthropic_key, "anthropic")
        if success:
            return

    # Check for OpenRouter API key
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key and openrouter_key != "your-key-here":
        success = _set_api_key(openrouter_key, "openrouter")
        if success:
            return


def _ensure_env_initialized() -> None:
    """Retry environment-backed setup for late Key Vault reference resolution."""

    if not _is_ai_enabled():
        _initialize_from_env()


def _get_ai_client():
    """Get the current AI client if available."""
    return _ai_config.get("client")


def _get_provider() -> ProviderType:
    """Get current provider."""
    return _ai_config.get("provider", "demo")


def _is_ai_enabled() -> bool:
    """Check if AI is enabled (API key is set)."""
    return _ai_config.get("client") is not None and _ai_config.get("provider") != "demo"


# Initialize on module load, after helpers it calls are defined.
_initialize_from_env()


def _get_model_name() -> str:
    """Get the model name based on provider."""
    provider = _get_provider()
    if provider == "anthropic":
        return _get_anthropic_model()
    elif provider == "openrouter":
        return _get_openrouter_model()
    else:
        return "ai-unavailable"


def _get_provider_display_name() -> str:
    """Get human-readable provider name."""
    provider = _get_provider()
    if provider == "anthropic":
        return "Anthropic API"
    elif provider == "openrouter":
        return "OpenRouter (Claude Max/Pro)"
    else:
        return "AI unavailable"


def _to_jsonable(value: Any) -> Any:
    """Convert Pydantic/domain objects into prompt-safe JSON values."""

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value


def _ai_unavailable_response() -> ChatResponse:
    """Return a truthful non-AI response without demo fleet facts."""

    return ChatResponse(
        response=(
            "AI is not currently available. The live FleetPulse dashboard remains the "
            "source of truth for vehicle counts, safety scores, alerts, and trip metrics."
        ),
        confidence=0.0,
        model="ai-unavailable",
        is_ai_powered=False,
    )


def _status_value(value: Any) -> str:
    """Return a stable lowercase status string for enum or string values."""

    return str(getattr(value, "value", value) or "").lower()


def _vehicle_name(vehicle: Any) -> str:
    return str(getattr(vehicle, "name", None) or getattr(vehicle, "id", None) or "Unknown vehicle").strip()


def _vehicle_speed(vehicle: Any) -> float | None:
    position = getattr(vehicle, "position", None)
    if position is None:
        return None
    try:
        return float(getattr(position, "speed", 0) or 0)
    except (TypeError, ValueError):
        return None


def _format_vehicle_summary(vehicle: Any) -> str:
    name = _vehicle_name(vehicle)
    speed = _vehicle_speed(vehicle)
    location = getattr(vehicle, "location_name", None)
    details: list[str] = []
    if speed is not None:
        details.append(f"speed {round(speed, 1)}")
    if location:
        details.append(str(location))
    return f"{name} ({'; '.join(details)})" if details else name


def _stop_value(stop: Any, field: str) -> Any:
    if isinstance(stop, dict):
        return stop.get(field)
    return getattr(stop, field, None)


def _format_long_stop(stop: Any) -> str:
    driver = _stop_value(stop, "driver_name") or _stop_value(stop, "driver_key") or "Unknown driver"
    device = _stop_value(stop, "device_name") or _stop_value(stop, "device_key")
    location = (
        _stop_value(stop, "location_label")
        or _stop_value(stop, "address")
        or _stop_value(stop, "geofence")
        or "location unavailable"
    )
    try:
        duration = float(_stop_value(stop, "duration_minutes") or 0)
    except (TypeError, ValueError):
        duration = 0
    subject = f"{driver} / {device}" if device else str(driver)
    if not _stop_value(stop, "resumed_at"):
        return f"{subject} currently at {location} for {duration:g} min"
    return f"{subject} at {location} for {duration:g} min"


def _long_stop_data(stop: Any) -> dict[str, Any]:
    return {
        "driver": _stop_value(stop, "driver_name") or _stop_value(stop, "driver_key"),
        "vehicle": _stop_value(stop, "device_name") or _stop_value(stop, "device_key"),
        "duration_minutes": _stop_value(stop, "duration_minutes"),
        "location": _stop_value(stop, "location_label"),
        "address": _stop_value(stop, "address"),
        "geofence": _stop_value(stop, "geofence"),
        "latitude": _stop_value(stop, "latitude"),
        "longitude": _stop_value(stop, "longitude"),
        "stopped_at": str(_stop_value(stop, "stopped_at") or ""),
        "resumed_at": str(_stop_value(stop, "resumed_at") or ""),
        "source_authority": _stop_value(stop, "source_authority") or "Geotab",
        "projection_mode": _stop_value(stop, "projection_mode") or "read_only",
    }


def _summarize_vehicle_names(vehicles: list[Any], *, limit: int = 12) -> str:
    if not vehicles:
        return "None in the current scoped FleetPulse snapshot."
    names = [_format_vehicle_summary(vehicle) for vehicle in vehicles[:limit]]
    extra_count = len(vehicles) - limit
    if extra_count > 0:
        names.append(f"+{extra_count} more")
    return ", ".join(names)


def _as_percent_text(value: Any) -> str:
    try:
        numeric = float(value or 0)
    except (TypeError, ValueError):
        numeric = 0.0
    if abs(numeric) <= 1:
        numeric *= 100
    return f"{numeric:.1f}%"


LANE_STABILITY_METRIC_DEFINITIONS = {
    "scored_lanes": (
        "Count of distinct Xcelerator service + lane combinations included in lane "
        "stability scoring for the current day/window. In the lakehouse daily KPI "
        "table this is total_lanes exposed as scored_lanes, and it is the denominator "
        "for stable lane coverage."
    ),
    "stable_lanes": "Scored lanes whose driver coverage is currently stable.",
    "stable_cov_pct": "Stable lane coverage percentage: stable lanes divided by scored lanes.",
    "critical_lanes": "Scored lanes in the critical stability band.",
    "cross_route_lanes": "Scored lanes being served across more than one route slot.",
    "total_orders": "Xcelerator order count represented in the lane stability projection.",
}


def _is_lane_stability_question(normalized: str) -> bool:
    if "lane" not in normalized:
        return False
    return any(
        term in normalized
        for term in (
            "scored",
            "score",
            "stability",
            "stable",
            "coverage",
            "critical",
            "cross route",
            "cross-route",
            "orders vs",
        )
    )


def _lane_stability_answer_from_payload(payload: dict[str, Any]) -> tuple[str, list[str], list[dict[str, Any]] | None]:
    summary = payload.get("summary") or {}
    rows = payload.get("rows") or []
    latest = rows[-1] if rows else {}
    scored_lanes = int(latest.get("scored_lanes") or 0)
    stable_lanes = int(latest.get("stable_lanes") or 0)
    stable_cov = latest.get("stable_cov_pct", summary.get("today_stable_cov_pct", 0))
    total_orders = int(latest.get("total_orders") or 0)
    snapshot_date = str(latest.get("snapshot_date") or "latest snapshot")
    critical_lanes = int(latest.get("critical_lanes") or summary.get("critical_today") or 0)
    cross_route_lanes = int(latest.get("cross_route_lanes") or summary.get("cross_route_today") or 0)

    response = (
        "Scored lanes are the lanes FleetPulse includes in the lane stability calculation. "
        "They are distinct Xcelerator service + lane combinations after excluding non-operational "
        "or service-only rows, and they are the denominator for stable lane coverage. "
        f"In the latest lane-stability snapshot ({snapshot_date}), FleetPulse has "
        f"{scored_lanes} scored lanes, {stable_lanes} stable lanes, "
        f"{_as_percent_text(stable_cov)} stable coverage, {critical_lanes} critical lanes, "
        f"{cross_route_lanes} cross-route lanes, and {total_orders} represented orders."
    )
    insights = [
        "If scored lanes increase, the denominator is broader; stable coverage can move even if stable lane count is flat.",
        "Critical lanes are the scored lanes that need the fastest operational review.",
        "Source: read-only Xcelerator/Fabric lane stability projection.",
    ]
    data = [
        {
            "location": "Scored lanes",
            "metric": "scored_lanes",
            "score": scored_lanes,
            "count": scored_lanes,
        },
        {
            "location": "Stable lanes",
            "metric": "stable_lanes",
            "score": stable_lanes,
            "count": stable_lanes,
        },
        {
            "location": "Critical lanes",
            "metric": "critical_lanes",
            "score": critical_lanes,
            "count": critical_lanes,
        },
        {
            "location": "Cross-route lanes",
            "metric": "cross_route_lanes",
            "score": cross_route_lanes,
            "count": cross_route_lanes,
        },
    ]
    return response, insights, data


def _is_address_benchmark_question(normalized: str) -> bool:
    if any(term in normalized for term in ("pickup", "delivery", "address")):
        return any(
            term in normalized
            for term in (
                "average",
                "avg",
                "history",
                "historical",
                "been there",
                "driver",
                "drivers",
                "faster",
                "time",
                "recording",
                "voice",
                "email",
                "worth",
            )
        )
    return (
        any(term in normalized for term in ("voice recording", "recording", "email"))
        and any(term in normalized for term in ("route", "driver", "pickup", "delivery", "stop"))
    )


def _address_pair_label(pair: dict[str, Any]) -> str:
    pickup = str(pair.get("pickup_address") or "pickup unavailable")
    delivery = str(pair.get("delivery_address") or "delivery unavailable")
    return f"{pickup} to {delivery}"


def _clean_address_filter(value: str | None) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n.,;:!?\"'")
    if not text:
        return None
    words = {word for word in re.split(r"\W+", text.casefold()) if word}
    generic_words = {
        "a",
        "address",
        "addresses",
        "all",
        "and",
        "any",
        "average",
        "avg",
        "before",
        "check",
        "compare",
        "delivery",
        "driver",
        "drivers",
        "email",
        "emails",
        "faster",
        "history",
        "pickup",
        "recording",
        "recordings",
        "route",
        "scan",
        "stop",
        "stops",
        "the",
        "time",
        "voice",
        "worth",
    }
    if words and words <= generic_words:
        return None
    return text[:120]


def _address_benchmark_filters_from_message(message: str) -> dict[str, str | None]:
    stop_terms = (
        r"(?=$|[?.!,;]|\s+(?:and\s+)?(?:compare|check|show|scan|history|historical|average|avg|drivers?|"
        r"faster|time|times|voice|recordings?|emails?|stops?|cost|worth|opportunity|for)\b)"
    )
    patterns = [
        rf"\bpickup(?:\s+address)?\s+(?P<pickup>.+?)\s+(?:delivery(?:\s+address)?|destination|drop\s*off)\s+(?P<delivery>.+?){stop_terms}",
        rf"\bfrom\s+(?P<pickup>.+?)\s+to\s+(?P<delivery>.+?){stop_terms}",
        rf"\bbetween\s+(?P<pickup>.+?)\s+and\s+(?P<delivery>.+?){stop_terms}",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if not match:
            continue
        pickup = _clean_address_filter(match.group("pickup"))
        delivery = _clean_address_filter(match.group("delivery"))
        if pickup and delivery:
            return {"pickup": pickup, "delivery": delivery}
    return {"pickup": None, "delivery": None}


def _address_filter_text(payload: dict[str, Any]) -> str:
    filters = payload.get("filters") or {}
    pickup = filters.get("pickup")
    delivery = filters.get("delivery")
    if pickup and delivery:
        return f" for pickup {pickup} and delivery {delivery}"
    if pickup:
        return f" for pickup {pickup}"
    if delivery:
        return f" for delivery {delivery}"
    return ""


def _minutes_text(value: Any) -> str:
    try:
        return f"{float(value):.1f} min"
    except (TypeError, ValueError):
        return "unavailable"


def _address_benchmark_answer_from_payload(payload: dict[str, Any]) -> tuple[str, list[str], list[dict[str, Any]] | None]:
    summary = payload.get("summary") or {}
    thresholds = payload.get("thresholds") or {}
    pairs = payload.get("address_pairs") or []
    evidence_sources = payload.get("evidence_sources") or {}
    period = payload.get("period") or {}
    stop_threshold = int(thresholds.get("stop_threshold_minutes") or 60)
    filter_text = _address_filter_text(payload)

    if not pairs:
        response = (
            "The historical pickup/delivery benchmark scan is available, but no measured "
            f"address pairs were returned{filter_text} for the current filter window. "
            f"FleetPulse checked {summary.get('route_rows_in_period', 0)} in-period route rows "
            f"from {payload.get('source_authority', 'read-only Xcelerator rows')}."
        )
        insights = [
            "Import or connect Xcelerator rows with actual pickup and delivery timestamps before comparing driver speed.",
            "Voice recordings and emails are only attached when a read-only evidence feed is configured.",
            f"The stop threshold for this scan is Stops >{stop_threshold}m.",
        ]
        return response, insights, None

    top_pairs = pairs[:3]
    pair_text = []
    data = []
    for pair in top_pairs:
        drivers = pair.get("driver_benchmarks") or []
        fastest = sorted(
            [driver for driver in drivers if driver.get("avg_route_minutes") is not None],
            key=lambda driver: float(driver.get("avg_route_minutes") or 0),
        )[:1]
        fastest_text = (
            f"; fastest driver {fastest[0].get('driver_name')} at {_minutes_text(fastest[0].get('avg_route_minutes'))}"
            if fastest
            else ""
        )
        pair_text.append(
            f"{_address_pair_label(pair)} averaged {_minutes_text(pair.get('avg_route_minutes'))} "
            f"across {pair.get('measured_orders', 0)} measured order(s){fastest_text}"
        )
        data.append(
            {
                "location": _address_pair_label(pair),
                "metric": "avg_route_minutes",
                "score": pair.get("avg_route_minutes") or 0,
                "avg_route_minutes": pair.get("avg_route_minutes"),
                "measured_orders": pair.get("measured_orders"),
                "stop_events_over_threshold": pair.get("stop_events_over_threshold"),
                "opportunity_minutes": pair.get("opportunity_minutes_vs_pair_average"),
                "voice_matches": (pair.get("evidence") or {}).get("voice_recordings", {}).get("match_count", 0),
                "email_matches": (pair.get("evidence") or {}).get("emails", {}).get("match_count", 0),
            }
        )

    response = (
        "FleetPulse can run the historical pickup/delivery scan as a read-only projection. "
        f"For {period.get('start', 'the window')} through {period.get('end', 'now')}{filter_text}, "
        f"it found {summary.get('address_pairs', 0)} address pair(s), "
        f"{summary.get('measured_orders', 0)} measured order(s), "
        f"{summary.get('drivers_compared', 0)} driver comparison(s), and "
        f"{_minutes_text(summary.get('opportunity_minutes_vs_pair_average'))} above pair averages. "
        + " Top lanes: "
        + "; ".join(pair_text)
        + "."
    )
    insights = [
        f"Stops >{stop_threshold}m are counted only from configured stop/dwell evidence.",
        f"Voice evidence status: {evidence_sources.get('status', 'pending_config')}; matched voice rows: {evidence_sources.get('voice_recordings', 0)}.",
        f"Email evidence status: {evidence_sources.get('status', 'pending_config')}; matched email rows: {evidence_sources.get('emails', 0)}.",
        "Xcelerator remains authoritative for route timing, revenue, driver pay, pickup, and delivery data.",
    ]
    return response, insights, data


async def _live_data_fallback_response(message: str) -> ChatResponse:
    """Answer supported live-data questions when the AI provider is unavailable."""

    normalized = message.lower()

    if _is_address_benchmark_question(normalized):
        try:
            from services.address_benchmark_service import get_address_benchmark_dataset

            filters = _address_benchmark_filters_from_message(message)
            benchmark_payload = get_address_benchmark_dataset(
                days=180,
                pickup=filters["pickup"],
                delivery=filters["delivery"],
            )
            response, insights, data = _address_benchmark_answer_from_payload(benchmark_payload)
            return ChatResponse(
                response=response,
                data=data,
                chart_type="bar" if data else None,
                insights=insights,
                confidence=0.75,
                model="live-data-fallback",
                is_ai_powered=False,
            )
        except Exception as exc:
            return ChatResponse(
                response=(
                    "The historical pickup/delivery benchmark scan is not available from "
                    f"the local projection right now ({type(exc).__name__})."
                ),
                insights=[
                    "Expected source: read-only Xcelerator ReviewOrders rows or Fabric Warehouse.",
                    "Voice/email evidence remains optional read-only annotation.",
                ],
                confidence=0.35,
                model="live-data-fallback",
                is_ai_powered=False,
            )

    from services.alert_service import get_recent_alerts
    from services.fleet_service import get_fleet_overview, get_vehicles
    from services.safety_service import get_safety_scores

    try:
        overview = get_fleet_overview()
    except Exception:
        return _ai_unavailable_response()

    response = ""
    data: list[dict[str, Any]] | None = None
    chart_type: str | None = None
    insights: list[str] = []

    if _is_lane_stability_question(normalized):
        try:
            from services.lakehouse_lane_stability_service import get_lane_stability_daily

            lane_payload = get_lane_stability_daily(window=42)
            response, insights, data = _lane_stability_answer_from_payload(lane_payload)
            chart_type = "bar"
        except Exception as exc:
            response = (
                "Scored lanes are the Xcelerator service + lane combinations included in "
                "FleetPulse lane stability scoring. They are the denominator for stable "
                "lane coverage. Current lane-stability values are unavailable from the "
                f"live projection right now ({type(exc).__name__})."
            )
            insights.append("Source expected: read-only Xcelerator/Fabric lane stability projection.")

    elif "active" in normalized and ("vehicle" in normalized or "truck" in normalized or "asset" in normalized):
        try:
            vehicles = get_vehicles()
            vehicles_loaded = True
        except Exception:
            vehicles = []
            vehicles_loaded = False
        active_vehicles = [
            vehicle
            for vehicle in vehicles
            if _status_value(getattr(vehicle, "status", "")) == "active"
        ]
        active_count = len(active_vehicles) if vehicles_loaded else overview.active
        response = (
            f"{active_count} of {overview.total_vehicles} scoped fleet vehicles are active right now. "
            f"Active vehicles: {_summarize_vehicle_names(active_vehicles)}"
        )
        data = [
            {
                "location": _vehicle_name(vehicle),
                "score": _vehicle_speed(vehicle) or 0,
                "vehicle": _vehicle_name(vehicle),
                "status": _status_value(getattr(vehicle, "status", "")),
                "speed": _vehicle_speed(vehicle),
                "location_name": getattr(vehicle, "location_name", None),
                "last_contact": str(getattr(vehicle, "last_contact", "") or ""),
            }
            for vehicle in active_vehicles
        ]
        chart_type = "bar" if data else None
        insights.append("Source: live Geotab-backed FleetPulse vehicle status.")

    elif "offline" in normalized or "risk" in normalized:
        try:
            vehicles = get_vehicles()
            vehicles_loaded = True
        except Exception:
            vehicles = []
            vehicles_loaded = False
        offline_vehicles = [
            vehicle
            for vehicle in vehicles
            if _status_value(getattr(vehicle, "status", "")) == "offline"
        ]
        offline_count = len(offline_vehicles) if vehicles_loaded else overview.offline
        response = (
            f"{offline_count} of {overview.total_vehicles} scoped fleet vehicles are offline. "
            f"Offline vehicles: {_summarize_vehicle_names(offline_vehicles)}"
        )
        insights.append("Offline units can indicate capacity, connectivity, or device-status risk.")

    elif (
        "trip" in normalized
        or "changed" in normalized
        or "stop" in normalized
        or "stopped" in normalized
        or "not moving" in normalized
    ):
        long_stops = list(getattr(overview, "long_stops_today", []) or [])
        response = (
            "Today's live trip summary: "
            f"{overview.total_trips_today} driver-session trips, "
            f"Stops >60m: {overview.total_stops_today}, "
            f"{overview.total_distance_miles:.1f} miles, "
            f"{overview.avg_trip_duration_hours:.1f} average trip hours, and "
            f"{overview.avg_trip_distance_miles:.1f} average miles per trip."
        )
        if long_stops:
            response += " Long stop locations: " + "; ".join(_format_long_stop(stop) for stop in long_stops[:5]) + "."
            data = [_long_stop_data(stop) for stop in long_stops]
        elif overview.total_stops_today:
            response += " No source-backed address or geofence detail is available for those Stops >60m in this refresh."
        insights.append(f"Trip definition: {overview.trip_definition}.")

    elif "safety" in normalized or "score" in normalized:
        try:
            scores = get_safety_scores()
        except Exception:
            scores = []
        attention_scores = sorted(
            [score for score in scores if getattr(score, "event_count", 0) > 0 or getattr(score, "score", 100) < 95],
            key=lambda score: (getattr(score, "score", 100), -getattr(score, "event_count", 0)),
        )
        if attention_scores:
            top = attention_scores[:5]
            response = (
                "Safety scores needing attention: "
                + ", ".join(
                    f"{getattr(score, 'vehicle_name', 'Unknown')} score {getattr(score, 'score', 'n/a')}"
                    f" with {getattr(score, 'event_count', 0)} event(s)"
                    for score in top
                )
            )
            data = [
                {
                    "location": getattr(score, "vehicle_name", "Unknown"),
                    "vehicle": getattr(score, "vehicle_name", "Unknown"),
                    "score": getattr(score, "score", None),
                    "events": getattr(score, "event_count", None),
                }
                for score in top
            ]
            chart_type = "bar"
        else:
            response = "No live safety-score exceptions were found in the current FleetPulse safety context."
        insights.append("Source: live FleetPulse safety scoring service.")

    elif "alert" in normalized or "exception" in normalized:
        try:
            alerts = get_recent_alerts()
        except Exception:
            alerts = []
        if alerts:
            response = (
                "Recent live alerts: "
                + ", ".join(
                    f"{getattr(alert, 'vehicle_name', 'Unknown')} {getattr(alert, 'alert_type', 'alert')}"
                    for alert in alerts[:5]
                )
            )
        else:
            response = "No active FleetPulse alerts were found in the current live alert feed."
        insights.append("Source: live FleetPulse alert service.")

    elif "utilization" in normalized or "fleet status" in normalized or "summarize" in normalized:
        total = max(overview.total_vehicles, 1)
        active_pct = round((overview.active / total) * 100, 1)
        response = (
            "Current live fleet status: "
            f"{overview.total_vehicles} scoped vehicles, {overview.active} active, "
            f"{overview.idle} idle, {overview.parked} parked, {overview.offline} offline. "
            f"Active utilization is {active_pct}%."
        )
        data = [
            {"location": "active", "status": "active", "count": overview.active, "score": overview.active},
            {"location": "idle", "status": "idle", "count": overview.idle, "score": overview.idle},
            {"location": "parked", "status": "parked", "count": overview.parked, "score": overview.parked},
            {"location": "offline", "status": "offline", "count": overview.offline, "score": overview.offline},
        ]
        chart_type = "bar"
        insights.append(f"Source mode: {overview.source_mode}.")

    else:
        response = (
            "AI is not currently available, but live FleetPulse data mode is online. "
            "I can answer supported questions about active vehicles, offline vehicles, "
            "fleet status, trips, alerts, utilization, and safety scores."
        )

    return ChatResponse(
        response=response,
        data=data,
        chart_type=chart_type,
        insights=insights or None,
        confidence=0.75 if response else 0.0,
        model="live-data-fallback",
        is_ai_powered=False,
    )


async def _fetch_fleet_context() -> str:
    """Fetch current fleet data to provide model context."""
    # Import here to avoid circular imports
    from services.fleet_service import get_fleet_overview
    from services.alert_service import get_recent_alerts
    from services.safety_service import get_safety_scores
    from services.lakehouse_lane_stability_service import get_lane_stability_daily
    from services.address_benchmark_service import get_address_benchmark_dataset

    context: dict[str, Any] = {
        "source_authority": "Geotab plus read-only Xcelerator/Fabric projections when included",
        "data_policy": (
            "Use only the values in this JSON. Do not infer, invent, or use "
            "sample/demo fleet values when a field is unavailable."
        ),
        "metric_definitions": {
            "lane_stability": LANE_STABILITY_METRIC_DEFINITIONS,
        },
    }

    try:
        context["fleet_overview"] = _to_jsonable(get_fleet_overview())
    except Exception as exc:
        context["fleet_overview_error"] = type(exc).__name__

    try:
        context["active_alerts"] = _to_jsonable(get_recent_alerts())[:20]
    except Exception as exc:
        context["active_alerts_error"] = type(exc).__name__

    try:
        context["safety_scores"] = _to_jsonable(get_safety_scores())[:20]
    except Exception as exc:
        context["safety_scores_error"] = type(exc).__name__

    try:
        lane_payload = _to_jsonable(get_lane_stability_daily(window=42))
        lane_rows = lane_payload.get("rows") or []
        context["lane_stability"] = {
            "source_authority": lane_payload.get("source_authority"),
            "projection_mode": lane_payload.get("projection_mode"),
            "window": lane_payload.get("window"),
            "generated_at": lane_payload.get("generated_at"),
            "summary": lane_payload.get("summary"),
            "latest_row": lane_rows[-1] if lane_rows else None,
            "recent_rows": lane_rows[-7:],
            "row_count": len(lane_rows),
        }
    except Exception as exc:
        context["lane_stability_error"] = type(exc).__name__

    try:
        benchmark_payload = _to_jsonable(get_address_benchmark_dataset(days=180))
        context["address_benchmarks"] = {
            "source_authority": benchmark_payload.get("source_authority"),
            "projection_mode": benchmark_payload.get("projection_mode"),
            "period": benchmark_payload.get("period"),
            "thresholds": benchmark_payload.get("thresholds"),
            "summary": benchmark_payload.get("summary"),
            "evidence_sources": benchmark_payload.get("evidence_sources"),
            "top_pairs": (benchmark_payload.get("address_pairs") or [])[:5],
        }
    except Exception as exc:
        context["address_benchmarks_error"] = type(exc).__name__

    return json.dumps(context, default=str)


CLAUDE_SYSTEM_PROMPT = """You are FleetPulse AI, an advanced fleet management intelligence assistant for K1 Logistics.

ABOUT FLEETPULSE:
FleetPulse is a GeoTab-powered fleet management platform that provides real-time analytics for:
- Vehicle tracking and utilization
- Safety scoring and incident management  
- Fuel and route metrics when present in the supplied context
- Maintenance and diagnostics when present in the supplied context
- Lane stability metrics from read-only Xcelerator/Fabric projections when present in the supplied context
- Pickup/delivery historical benchmark metrics from read-only Xcelerator projections when present in the supplied context
- Driver behavior analysis
- Cost optimization only when the supplied data supports it

YOUR ROLE:
- Analyze the current FleetPulse context supplied with each request
- Answer questions about vehicle performance, safety, utilization, alerts, and trips
- Generate charts and visualizations when the supplied context contains enough data
- Provide specific recommendations grounded in the supplied context
- Explain complex fleet metrics in simple terms
- Never invent fleet metrics, vehicle IDs, costs, maintenance predictions, or location facts.
- If a value is unavailable in the supplied current fleet data, say it is unavailable instead of using demo/sample data.
- Do not describe the supplied FleetPulse context as fixed, sample data, or demo data.
- If the user asks to refresh data, explain that this response uses the latest available FleetPulse context fetched for the current request.
- If the user asks what a metric means, first use metric_definitions from the supplied context, then include current values when they are present.

RESPONSE FORMAT:
Always provide:
1. Direct answer to the question
2. Supporting data (if relevant) 
3. Actionable insights or recommendations
4. Potential cost impact/savings only when supported by the supplied context

For visualizations, structure your response with:
- response: Main answer text
- data: Array of objects for charting
- chart_type: "bar", "line", or "pie"  
- insights: Array of key takeaways

Be data-driven, specific, and focus on operational improvements that save money or improve safety."""


def _build_current_message(fleet_context: str, message: str) -> str:
    """Build a prompt chunk that clearly frames FleetPulse data as live context."""

    return f"""CURRENT LIVE FLEETPULSE CONTEXT:
The JSON below was fetched for this request from Geotab-backed FleetPulse services.
It is not static, sample, or demo data. Use only these values.

{fleet_context}

USER QUESTION: {message}

Analyze the question using the current FleetPulse context. If a requested metric is
not in the context, say it is unavailable instead of guessing."""


class ChatMessage(BaseModel):
    message: str
    conversation_history: Optional[List[Dict[str, str]]] = []
    timestamp: Optional[datetime] = None


class ChatResponse(BaseModel):
    response: str
    data: Optional[List[Dict[str, Any]]] = None
    chart_type: Optional[str] = None
    insights: Optional[List[str]] = None
    confidence: float = 0.95
    model: Optional[str] = None
    is_ai_powered: bool = False


class FleetInsight(BaseModel):
    type: str
    priority: str
    title: str
    message: str
    impact: str
    action: str


class ApiKeyRequest(BaseModel):
    api_key: str
    provider: ProviderType = "anthropic"


class ConfigResponse(BaseModel):
    ai_enabled: bool
    model: Optional[str] = None
    provider: ProviderType = "demo"
    provider_name: str = "AI unavailable"



async def _process_ai_query(message: str, conversation_history: List[Dict[str, str]]) -> ChatResponse:
    """Process query using AI (Anthropic or OpenRouter)."""
    client = _get_ai_client()
    provider = _get_provider()
    
    if not client or provider == "demo":
        raise HTTPException(status_code=503, detail="AI service not available")
    
    try:
        # Fetch current fleet context
        fleet_context = await _fetch_fleet_context()
        
        # Build conversation history
        messages = []
        
        # Add conversation history
        for msg in conversation_history[-10:]:  # Last 10 messages for context
            role = "user" if msg.get("type") == "user" else "assistant"
            messages.append({"role": role, "content": msg.get("content", "")})
        
        # Add current message with fleet context
        current_message = _build_current_message(fleet_context, message)

        messages.append({"role": "user", "content": current_message})
        
        # Call AI service based on provider
        response_text = ""
        
        if provider == "anthropic":
            # Direct Anthropic API
            response = client.messages.create(
                model=_get_anthropic_model(),
                max_tokens=2000,
                system=CLAUDE_SYSTEM_PROMPT,
                messages=messages
            )
            response_text = response.content[0].text
            
        elif provider == "openrouter":
            # OpenRouter (OpenAI-compatible)
            openai_messages = [{"role": "system", "content": CLAUDE_SYSTEM_PROMPT}] + messages
            
            response = client.chat.completions.create(
                model=_get_openrouter_model(),
                messages=openai_messages,
                max_tokens=2000,
                temperature=0.7
            )
            response_text = response.choices[0].message.content
        
        # Parse response for structured data
        chart_type = None
        data = None
        insights = []
        
        # Look for chart suggestions in response
        if "bar chart" in response_text.lower() or "bar graph" in response_text.lower():
            chart_type = "bar"
        elif "line chart" in response_text.lower() or "trend" in response_text.lower():
            chart_type = "line"  
        elif "pie chart" in response_text.lower() or "distribution" in response_text.lower():
            chart_type = "pie"
        
        # Extract insights (lines starting with bullet points or numbers)
        lines = response_text.split('\n')
        for line in lines:
            line = line.strip()
            if (line.startswith('•') or line.startswith('-') or 
                line.startswith('*') or re.match(r'^\d+\.', line)):
                insights.append(line.lstrip('•-* ').lstrip('0123456789. '))
        
        # If AI suggested a specific visualization, try to provide relevant data
        # Do not attach sample chart payloads. The model response should only
        # describe values that were present in the live context above.
        
        return ChatResponse(
            response=response_text,
            data=data,
            chart_type=chart_type,
            insights=insights[:3],  # Top 3 insights
            confidence=0.95,
            model=_get_model_name(),
            is_ai_powered=True
        )
        
    except Exception as e:
        print(f"{provider} API error: {e}")
        return _ai_unavailable_response()


@router.post("/chat", response_model=ChatResponse)
async def process_chat_query(chat_message: ChatMessage):
    """Process a natural language fleet query with Claude AI or fallback to pattern matching."""
    try:
        _ensure_env_initialized()
        if _is_ai_enabled():
            return await _process_ai_query(
                chat_message.message, 
                chat_message.conversation_history or []
            )
        else:
            return await _live_data_fallback_response(chat_message.message)
        
    except Exception as e:
        print(f"Error in chat processing: {e}")
        # Ultimate fallback
        return ChatResponse(
            response="I'm experiencing technical difficulties. Please try rephrasing your question or check specific metrics in the dashboard.",
            confidence=0.1,
            model="error-fallback",
            is_ai_powered=False
        )


# Legacy endpoint for backward compatibility
@router.post("/query", response_model=ChatResponse)
async def process_legacy_query(chat_message: ChatMessage):
    """Legacy endpoint - redirects to new chat endpoint."""
    return await process_chat_query(chat_message)


@router.post("/chat/stream")
async def process_chat_stream(chat_message: ChatMessage):
    """Process chat query with streaming response (Server-Sent Events)."""
    
    async def stream_response():
        _ensure_env_initialized()
        if not _is_ai_enabled():
            response = await _live_data_fallback_response(chat_message.message)
            yield f"data: {json.dumps({'chunk': response.response, 'type': 'text'})}\n\n"
            final_data = response.dict()
            final_data["type"] = "complete"
            yield f"data: {json.dumps(final_data)}\n\n"
            return
        
        client = _get_ai_client()
        provider = _get_provider()
        
        if not client:
            yield f"data: {json.dumps({'error': 'AI service not available'})}\n\n"
            return
        
        try:
            # Fetch fleet context
            fleet_context = await _fetch_fleet_context()
            
            # Build conversation history
            messages = []
            for msg in chat_message.conversation_history[-10:]:
                role = "user" if msg.get("type") == "user" else "assistant"
                messages.append({"role": role, "content": msg.get("content", "")})
            
            current_message = _build_current_message(fleet_context, chat_message.message)

            messages.append({"role": "user", "content": current_message})
            
            accumulated_text = ""
            
            if provider == "anthropic":
                # Stream from Anthropic
                with client.messages.stream(
                    model=_get_anthropic_model(),
                    max_tokens=2000,
                    system=CLAUDE_SYSTEM_PROMPT,
                    messages=messages
                ) as stream:
                    for chunk in stream:
                        if chunk.type == "content_block_delta":
                            if chunk.delta.type == "text_delta":
                                text_chunk = chunk.delta.text
                                accumulated_text += text_chunk
                                yield f"data: {json.dumps({'chunk': text_chunk, 'type': 'text'})}\n\n"
                                
            elif provider == "openrouter":
                # Stream from OpenRouter
                openai_messages = [{"role": "system", "content": CLAUDE_SYSTEM_PROMPT}] + messages
                
                stream = client.chat.completions.create(
                    model=_get_openrouter_model(),
                    messages=openai_messages,
                    max_tokens=2000,
                    temperature=0.7,
                    stream=True
                )
                
                for chunk in stream:
                    if chunk.choices[0].delta.content is not None:
                        text_chunk = chunk.choices[0].delta.content
                        accumulated_text += text_chunk
                        yield f"data: {json.dumps({'chunk': text_chunk, 'type': 'text'})}\n\n"
            
            # After streaming is complete, analyze for charts and insights
            chart_type = None
            data = None
            insights = []
            
            # Analyze accumulated text for visualizations
            if "bar chart" in accumulated_text.lower():
                chart_type = "bar"
            elif "line chart" in accumulated_text.lower():
                chart_type = "line"  
            elif "pie chart" in accumulated_text.lower():
                chart_type = "pie"
            
            # Extract insights
            lines = accumulated_text.split('\n')
            for line in lines:
                line = line.strip()
                if (line.startswith('•') or line.startswith('-') or 
                    line.startswith('*') or re.match(r'^\d+\.', line)):
                    insights.append(line.lstrip('•-* ').lstrip('0123456789. '))
            
            # Do not attach sample chart payloads. The model response should
            # only describe values present in the live context above.
            
            # Send final metadata
            final_data = {
                'type': 'complete',
                'chart_type': chart_type,
                'data': data,
                'insights': insights[:3],
                'model': _get_model_name(),
                'is_ai_powered': True
            }
            yield f"data: {json.dumps(final_data)}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'error': f'Streaming error: {str(e)}'})}\n\n"
    
    return StreamingResponse(
        stream_response(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        }
    )


@router.post("/config")
async def set_api_key(request: ApiKeyRequest):
    """Set API key and provider in memory (not persisted to disk)."""
    try:
        success = _set_api_key(request.api_key, request.provider)
        if success:
            provider_name = _get_provider_display_name()
            return {
                "message": f"API key configured successfully for {provider_name}",
                "ai_enabled": True,
                "provider": request.provider
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid API key or failed to connect to {request.provider.title()}"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error setting API key: {str(e)}"
        )


@router.get("/config", response_model=ConfigResponse)
async def get_ai_config():
    """Get current AI configuration status (never returns the API key)."""
    _ensure_env_initialized()
    provider = _get_provider()
    return ConfigResponse(
        ai_enabled=_is_ai_enabled(),
        model=_get_model_name() if _is_ai_enabled() else None,
        provider=provider,
        provider_name=_get_provider_display_name()
    )


@router.get("/insights", response_model=List[FleetInsight])
async def get_ai_insights():
    """Get fleet insights derived from live Geotab-backed services."""

    from services.alert_service import get_recent_alerts
    from services.fleet_service import get_fleet_overview
    from services.safety_service import get_safety_scores

    insights: list[FleetInsight] = []
    overview = get_fleet_overview()
    total = max(overview.total_vehicles, 1)
    utilization_rate = round((overview.active / total) * 100, 1)

    if overview.offline:
        priority = "high" if overview.offline / total >= 0.2 else "medium"
        insights.append(FleetInsight(
            type="availability",
            priority=priority,
            title="Offline Vehicle Review",
            message=f"{overview.offline} of {overview.total_vehicles} scoped vehicles are offline in the latest Geotab status snapshot.",
            impact="Capacity risk; verify device connectivity and vehicle availability.",
            action="Review Offline Vehicles"
        ))

    if utilization_rate < 20:
        insights.append(FleetInsight(
            type="utilization",
            priority="medium",
            title="Low Active Utilization",
            message=f"{overview.active} of {overview.total_vehicles} scoped vehicles are active now ({utilization_rate}%).",
            impact="Potential under-utilization; compare against dispatch plan before taking action.",
            action="Review Dispatch Plan"
        ))

    alerts = get_recent_alerts()
    if alerts:
        top_alert = alerts[0]
        insights.append(FleetInsight(
            type="alert",
            priority=str(top_alert.severity.value),
            title="Recent Geotab Alert",
            message=f"{top_alert.alert_type} reported for {top_alert.vehicle_name}.",
            impact="Operational risk from live Geotab exception data.",
            action="Open Alert Feed"
        ))

    safety_scores = get_safety_scores()
    attention_scores = [score for score in safety_scores if score.event_count > 0 or score.score < 95]
    if attention_scores:
        attention_scores.sort(key=lambda score: (score.score, -score.event_count))
        score = attention_scores[0]
        insights.append(FleetInsight(
            type="safety",
            priority="medium" if score.score >= 80 else "high",
            title="Safety Score Attention",
            message=f"{score.vehicle_name} has safety score {score.score} with {score.event_count} recent event(s).",
            impact="Safety coaching opportunity from live Geotab events.",
            action="Review Safety Detail"
        ))

    if not insights:
        insights.append(FleetInsight(
            type="status",
            priority="low",
            title="No Active Fleet Exceptions",
            message="No live alerts or safety exceptions were found in the latest FleetPulse context.",
            impact="Continue monitoring live Geotab-backed dashboard metrics.",
            action="Monitor Dashboard"
        ))

    return insights[:4]


@router.get("/analytics/summary")
async def get_analytics_summary():
    """Get comprehensive fleet analytics summary from live services."""
    from services.alert_service import get_recent_alerts
    from services.fleet_service import get_fleet_overview
    from services.safety_service import get_safety_scores

    overview = get_fleet_overview()
    alerts = get_recent_alerts()
    safety_scores = get_safety_scores()

    total = max(overview.total_vehicles, 1)
    utilization_rate = round((overview.active / total) * 100, 1)
    avg_safety_score = (
        round(sum(score.score for score in safety_scores) / len(safety_scores), 1)
        if safety_scores else None
    )
    safety_events = sum(score.event_count for score in safety_scores)
    high_alerts = [
        alert for alert in alerts
        if str(alert.severity.value) in {"high", "critical"}
    ]

    return {
        "source_authority": "Geotab",
        "source_mode": overview.source_mode,
        "data_policy": "Live FleetPulse summary only; unavailable values are null, not estimated.",
        "fleet_health": {
            "overall_score": avg_safety_score,
            "safety_trend": "stable" if safety_scores else "unavailable",
            "efficiency_trend": "unavailable",
            "utilization_rate": utilization_rate,
            "maintenance_compliance": None
        },
        "key_metrics": {
            "total_vehicles": overview.total_vehicles,
            "active_vehicles": overview.active,
            "parked_vehicles": overview.parked,
            "offline_vehicles": overview.offline,
            "total_trips_today": overview.total_trips_today,
            "total_stops_today": overview.total_stops_today,
            "total_distance_miles": overview.total_distance_miles,
            "avg_safety_score": avg_safety_score,
            "avg_fuel_efficiency": None,
            "monthly_savings_potential": None
        },
        "risk_indicators": [
            {
                "type": "offline_vehicles",
                "risk": "high" if overview.offline / total >= 0.2 else "medium",
                "count": overview.offline,
                "reason": "vehicle_status_offline"
            },
            {
                "type": "high_severity_alerts",
                "risk": "high" if high_alerts else "low",
                "count": len(high_alerts),
                "reason": "geotab_exception_events"
            },
            {
                "type": "safety_events",
                "risk": "medium" if safety_events else "low",
                "count": safety_events,
                "reason": "geotab_safety_score_events"
            }
        ],
        "optimization_opportunities": [
            {"type": "restore_offline_capacity", "impact": "high" if overview.offline else "low", "savings": None},
            {"type": "review_low_utilization", "impact": "medium" if utilization_rate < 20 else "low", "savings": None},
            {"type": "review_safety_events", "impact": "medium" if safety_events else "low", "savings": None}
        ]
    }
