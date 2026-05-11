"""Tests for FleetPulse AI provider configuration."""

from __future__ import annotations

import importlib
import asyncio
import json
import sys
from pathlib import Path


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

    context = asyncio.run(ai_chat._fetch_fleet_context())
    parsed = json.loads(context)

    assert parsed["fleet_overview"]["total_vehicles"] == 45
    assert parsed["fleet_overview"]["raw_device_count"] == 759
    assert parsed["safety_scores"][0]["vehicle_id"] == "truck-1"
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
