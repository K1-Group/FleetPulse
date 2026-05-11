"""Tests for FleetPulse AI provider configuration."""

from __future__ import annotations

import importlib
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
