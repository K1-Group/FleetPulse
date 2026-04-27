"""Tests for the data_connector router's Jurisdiction Mismatch handling.

These run without a live Geotab account by stubbing the OData responses.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

# Make backend/ importable regardless of how pytest is invoked.
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Stub mygeotab so geotab_client imports without the SDK installed.
if "mygeotab" not in sys.modules:
    fake = types.ModuleType("mygeotab")
    class _FakeAPI:  # noqa: D401
        def __init__(self, *a, **kw):
            pass
        def authenticate(self):
            pass
        def call(self, *a, **kw):
            return []
    fake.API = _FakeAPI
    sys.modules["mygeotab"] = fake


@pytest.fixture(autouse=True)
def _stub_geotab_creds(monkeypatch):
    monkeypatch.setenv("GEOTAB_USERNAME", "u")
    monkeypatch.setenv("GEOTAB_PASSWORD", "p")
    monkeypatch.setenv("GEOTAB_DATABASE", "k1logistics")
    monkeypatch.delenv("GEOTAB_ODATA_SERVER", raising=False)
    yield


def _import_router_fresh():
    # data_connector caches the chosen server in module-global state, so we
    # always reload it for a clean slate per test.
    import importlib

    if "routers.data_connector" in sys.modules:
        del sys.modules["routers.data_connector"]
    return importlib.import_module("routers.data_connector")


def test_jurisdiction_helper_detects_message():
    mod = _import_router_fresh()
    assert mod._is_jurisdiction_error('{"message":"Jurisdiction Mismatch"}') is True
    assert mod._is_jurisdiction_error("totally fine") is False
    assert mod._is_jurisdiction_error("") is False


def test_pinned_server_skips_discovery(monkeypatch):
    monkeypatch.setenv(
        "GEOTAB_ODATA_SERVER",
        "https://odata-connector-7.geotab.com/odata/v4/svc/",
    )
    mod = _import_router_fresh()

    import asyncio

    async def _go():
        return await mod._find_server()

    result = asyncio.run(_go())
    assert result == "https://odata-connector-7.geotab.com/odata/v4/svc/"


def test_pinned_server_appends_trailing_slash(monkeypatch):
    monkeypatch.setenv(
        "GEOTAB_ODATA_SERVER",
        "https://odata-connector-3.geotab.com/odata/v4/svc",  # no slash
    )
    mod = _import_router_fresh()

    import asyncio

    async def _go():
        return await mod._find_server()

    assert asyncio.run(_go()).endswith("/")


def test_invalidate_clears_cache():
    mod = _import_router_fresh()
    mod._ODATA_SERVER = "https://odata-connector-9.geotab.com/odata/v4/svc/"

    import asyncio

    asyncio.run(mod._invalidate_server())
    assert mod._ODATA_SERVER is None


def test_jurisdiction_mismatch_class_carries_detail():
    mod = _import_router_fresh()
    exc = mod._JurisdictionMismatch("body excerpt")
    assert exc.detail == "body excerpt"
    assert "body excerpt" in str(exc)


def test_servers_list_extended_to_15():
    """Defensive: ensure we did not regress the broader probe range."""
    mod = _import_router_fresh()
    assert len(mod._ODATA_SERVERS) == 15
    assert mod._ODATA_SERVERS[0].startswith("https://odata-connector-1.geotab.com/")
    assert mod._ODATA_SERVERS[-1].startswith("https://odata-connector-15.geotab.com/")
