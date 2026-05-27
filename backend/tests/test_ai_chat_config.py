"""Tests for FleetPulse AI provider configuration."""

from __future__ import annotations

import importlib
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace


BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def _load_ai_chat(monkeypatch):
    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
        "OPENROUTER_SITE_URL",
        "OPENROUTER_APP_NAME",
    ):
        monkeypatch.delenv(name, raising=False)
    sys.modules.pop("routers.ai_chat", None)
    return importlib.import_module("routers.ai_chat")


def test_openrouter_model_defaults_to_current_openrouter_id(monkeypatch):
    ai_chat = _load_ai_chat(monkeypatch)
    ai_chat._ai_config = {"provider": "openrouter", "api_key": None, "client": object()}

    assert ai_chat._get_model_name() == "anthropic/claude-sonnet-4"


def test_openrouter_model_can_be_overridden(monkeypatch):
    ai_chat = _load_ai_chat(monkeypatch)
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")
    ai_chat._ai_config = {"provider": "openrouter", "api_key": None, "client": object()}

    assert ai_chat._get_model_name() == "anthropic/claude-sonnet-4.5"


def test_openrouter_client_uses_optional_attribution_headers(monkeypatch):
    ai_chat = _load_ai_chat(monkeypatch)
    captured: dict = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(ai_chat.openai, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENROUTER_SITE_URL", "https://k1-fleetpulse.azurewebsites.net")
    monkeypatch.setenv("OPENROUTER_APP_NAME", "FleetPulse")

    ai_chat._build_openrouter_client("secret-value")

    assert captured["base_url"] == "https://openrouter.ai/api/v1"
    assert captured["api_key"] == "secret-value"
    assert captured["default_headers"] == {
        "HTTP-Referer": "https://k1-fleetpulse.azurewebsites.net",
        "X-Title": "FleetPulse",
    }


def test_openrouter_validation_uses_configured_model(monkeypatch):
    ai_chat = _load_ai_chat(monkeypatch)
    captured: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return object()

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        chat = FakeChat()

        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

    monkeypatch.setattr(ai_chat.openai, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")

    assert ai_chat._set_api_key("secret-value", "openrouter") is True
    assert captured["model"] == "anthropic/claude-sonnet-4.5"
    assert "secret-value" not in str(captured["messages"])


def test_openrouter_env_key_initializes_on_import(monkeypatch):
    import openai

    captured: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return object()

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        chat = FakeChat()

        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-value")
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sys.modules.pop("routers.ai_chat", None)

    ai_chat = importlib.import_module("routers.ai_chat")

    assert ai_chat._is_ai_enabled() is True
    assert ai_chat._get_provider() == "openrouter"
    assert captured["model"] == "anthropic/claude-sonnet-4"


def test_fleet_context_uses_live_services_without_demo_values(monkeypatch):
    ai_chat = _load_ai_chat(monkeypatch)

    class FakeOverview:
        def model_dump(self, **_kwargs):
            return {
                "total_vehicles": 45,
                "raw_device_count": 759,
                "scoped_device_count": 45,
                "source_authority": "Geotab",
            }

    class FakeSafety:
        def model_dump(self, **_kwargs):
            return {"vehicle_id": "truck-1", "vehicle_name": "Truck 1", "score": 100}

    monkeypatch.setattr("services.fleet_service.get_fleet_overview", lambda: FakeOverview())
    monkeypatch.setattr("services.alert_service.get_recent_alerts", lambda: [])
    monkeypatch.setattr("services.safety_service.get_safety_scores", lambda: [FakeSafety()])
    monkeypatch.setattr(
        "services.lakehouse_lane_stability_service.get_lane_stability_daily",
        lambda window=42: {
            "window": window,
            "generated_at": "2026-05-21T14:00:00+00:00",
            "source_authority": "K1 Group LLC / Fabric lakehouse lane_stability_daily_kpi",
            "projection_mode": "read_only",
            "rows": [
                {
                    "snapshot_date": "2026-05-21",
                    "stable_cov_pct": 0.82,
                    "critical_lanes": 2,
                    "cross_route_lanes": 6,
                    "total_orders": 140,
                    "scored_lanes": 50,
                    "stable_lanes": 41,
                    "total_revenue": 65000.0,
                    "delta_cov_pp": 1.2,
                }
            ],
            "summary": {
                "today_stable_cov_pct": 0.82,
                "wow_delta_pp": 1.2,
                "critical_today": 2,
                "cross_route_today": 6,
                "revenue_wtd": 65000.0,
            },
        },
    )

    context = asyncio.run(ai_chat._fetch_fleet_context())
    parsed = json.loads(context)

    assert parsed["fleet_overview"]["total_vehicles"] == 45
    assert parsed["fleet_overview"]["raw_device_count"] == 759
    assert parsed["safety_scores"][0]["vehicle_id"] == "truck-1"
    assert parsed["metric_definitions"]["lane_stability"]["scored_lanes"]
    assert parsed["lane_stability"]["latest_row"]["scored_lanes"] == 50
    assert "V018" not in context
    assert "Fort Worth" not in context
    assert "180" not in context


def test_ai_system_prompt_does_not_embed_demo_locations(monkeypatch):
    ai_chat = _load_ai_chat(monkeypatch)

    assert "Fort Worth" not in ai_chat.CLAUDE_SYSTEM_PROMPT
    assert "OKC" not in ai_chat.CLAUDE_SYSTEM_PROMPT
    assert "static dataset" not in ai_chat.CLAUDE_SYSTEM_PROMPT.lower()
    assert "demo data" in ai_chat.CLAUDE_SYSTEM_PROMPT.lower()


def test_current_message_frames_context_as_live_not_static(monkeypatch):
    ai_chat = _load_ai_chat(monkeypatch)

    prompt = ai_chat._build_current_message('{"total_vehicles": 45}', "refresh data")

    assert "CURRENT LIVE FLEETPULSE CONTEXT" in prompt
    assert "fetched for this request" in prompt
    assert "It is not static, sample, or demo data" in prompt
    assert "USER QUESTION: refresh data" in prompt


def test_live_data_fallback_answers_active_vehicle_question(monkeypatch):
    ai_chat = _load_ai_chat(monkeypatch)

    overview = SimpleNamespace(
        active=2,
        avg_trip_distance_miles=0,
        avg_trip_duration_hours=0,
        idle=0,
        offline=1,
        parked=1,
        source_mode="live_filtered",
        total_distance_miles=0,
        total_stops_today=0,
        total_trips_today=0,
        total_vehicles=4,
        trip_definition="driver_session_with_stops_over_60_min",
    )
    vehicles = [
        SimpleNamespace(
            id="b1",
            name="8763",
            status="active",
            position=SimpleNamespace(speed=112),
            location_name=None,
            last_contact="2026-05-14T04:11:44Z",
        ),
        SimpleNamespace(
            id="b2",
            name="6417",
            status="active",
            position=SimpleNamespace(speed=81),
            location_name=None,
            last_contact="2026-05-14T04:11:55Z",
        ),
        SimpleNamespace(id="b3", name="7754", status="parked", position=None),
        SimpleNamespace(id="b4", name="2743", status="offline", position=None),
    ]

    monkeypatch.setattr("services.fleet_service.get_fleet_overview", lambda: overview)
    monkeypatch.setattr("services.fleet_service.get_vehicles", lambda: vehicles)
    monkeypatch.setattr("services.alert_service.get_recent_alerts", lambda: [])
    monkeypatch.setattr("services.safety_service.get_safety_scores", lambda: [])

    response = asyncio.run(
        ai_chat.process_chat_query(
            ai_chat.ChatMessage(message="Which vehicles are active right now?")
        )
    )

    assert response.model == "live-data-fallback"
    assert response.is_ai_powered is False
    assert "2 of 4 scoped fleet vehicles are active right now" in response.response
    assert "8763" in response.response
    assert "6417" in response.response
    assert response.data[0]["vehicle"] == "8763"
    assert response.data[0]["score"] == 112


def test_live_data_fallback_summarizes_fleet_status(monkeypatch):
    ai_chat = _load_ai_chat(monkeypatch)

    overview = SimpleNamespace(
        active=6,
        avg_trip_distance_miles=247.3,
        avg_trip_duration_hours=8.2,
        idle=0,
        offline=3,
        parked=36,
        source_mode="live_filtered",
        total_distance_miles=17313.1,
        total_stops_today=436,
        total_trips_today=70,
        total_vehicles=45,
        trip_definition="driver_session_with_stops_over_60_min",
    )

    monkeypatch.setattr("services.fleet_service.get_fleet_overview", lambda: overview)
    monkeypatch.setattr("services.fleet_service.get_vehicles", lambda: [])
    monkeypatch.setattr("services.alert_service.get_recent_alerts", lambda: [])
    monkeypatch.setattr("services.safety_service.get_safety_scores", lambda: [])

    response = asyncio.run(
        ai_chat.process_chat_query(
            ai_chat.ChatMessage(message="Summarize current fleet status")
        )
    )

    assert response.model == "live-data-fallback"
    assert "45 scoped vehicles" in response.response
    assert "6 active" in response.response
    assert "13.3%" in response.response


def test_live_data_fallback_explains_scored_lanes(monkeypatch):
    ai_chat = _load_ai_chat(monkeypatch)

    overview = SimpleNamespace(
        active=6,
        avg_trip_distance_miles=247.3,
        avg_trip_duration_hours=8.2,
        idle=0,
        offline=3,
        parked=36,
        source_mode="live_filtered",
        total_distance_miles=17313.1,
        total_stops_today=436,
        total_trips_today=70,
        total_vehicles=45,
        trip_definition="driver_session_with_stops_over_60_min",
    )

    monkeypatch.setattr("services.fleet_service.get_fleet_overview", lambda: overview)
    monkeypatch.setattr("services.alert_service.get_recent_alerts", lambda: [])
    monkeypatch.setattr("services.safety_service.get_safety_scores", lambda: [])
    monkeypatch.setattr(
        "services.lakehouse_lane_stability_service.get_lane_stability_daily",
        lambda window=42: {
            "window": window,
            "generated_at": "2026-05-21T14:00:00+00:00",
            "source_authority": "K1 Group LLC / Fabric lakehouse lane_stability_daily_kpi",
            "projection_mode": "read_only",
            "rows": [
                {
                    "snapshot_date": "2026-05-21",
                    "stable_cov_pct": 0.82,
                    "critical_lanes": 2,
                    "cross_route_lanes": 6,
                    "total_orders": 140,
                    "scored_lanes": 50,
                    "stable_lanes": 41,
                    "total_revenue": 65000.0,
                    "delta_cov_pp": 1.2,
                }
            ],
            "summary": {
                "today_stable_cov_pct": 0.82,
                "wow_delta_pp": 1.2,
                "critical_today": 2,
                "cross_route_today": 6,
                "revenue_wtd": 65000.0,
            },
        },
    )

    response = asyncio.run(
        ai_chat.process_chat_query(
            ai_chat.ChatMessage(message="What does scored lanes mean?")
        )
    )

    assert response.model == "live-data-fallback"
    assert response.is_ai_powered is False
    assert "Scored lanes are the lanes FleetPulse includes in the lane stability calculation" in response.response
    assert "50 scored lanes" in response.response
    assert "41 stable lanes" in response.response
    assert "82.0% stable coverage" in response.response
    assert response.chart_type == "bar"
    assert response.data[0]["metric"] == "scored_lanes"
