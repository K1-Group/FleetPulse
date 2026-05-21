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
    from _cache import clear_cached_prefix

    clear_cached_prefix("data-connector:")
    monkeypatch.setenv("GEOTAB_USERNAME", "u")
    monkeypatch.setenv("GEOTAB_PASSWORD", "p")
    monkeypatch.setenv("GEOTAB_DATABASE", "k1logistics")
    monkeypatch.delenv("GEOTAB_ODATA_SERVER", raising=False)
    yield
    clear_cached_prefix("data-connector:")


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


def test_missing_metadata_helper_detects_geotab_message():
    mod = _import_router_fresh()
    assert mod._is_missing_metadata_error('{"message":"Metadata is Not Found"}') is True
    assert mod._is_missing_metadata_error("other error") is False


def test_basic_auth_username_adds_database_prefix():
    mod = _import_router_fresh()
    assert mod._odata_auth_username("K1logistics", "AI_Enterprise@example.com") == (
        "K1logistics/AI_Enterprise@example.com"
    )


def test_basic_auth_username_does_not_double_prefix():
    mod = _import_router_fresh()
    assert mod._odata_auth_username("K1logistics", "K1logistics/AI_Enterprise@example.com") == (
        "K1logistics/AI_Enterprise@example.com"
    )


def test_status_is_sanitized_and_reports_auth_shape(monkeypatch):
    mod = _import_router_fresh()
    monkeypatch.setenv("GEOTAB_PASSWORD", "super-secret")
    mod.GeotabClient._instance = None

    status = mod._data_connector_config_status()

    assert status["password_configured"] is True
    assert status["basic_auth_username_format"] == "<database>/<username>"
    assert status["basic_auth_database_matches_env"] is True
    assert "super-secret" not in str(status)
    assert "AI_Enterprise" not in str(status)


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


def test_redirect_base_extracts_numbered_service_root():
    mod = _import_router_fresh()

    assert (
        mod._odata_base_from_url(
            "https://odata-connector-12.geotab.com/odata/v4/svc/"
            "LatestVehicleMetadata?$search=last_1_day&$top=1"
        )
        == "https://odata-connector-12.geotab.com/odata/v4/svc/"
    )
    assert mod._odata_base_from_url("https://example.com/not-odata") is None
    assert (
        mod._normalize_server(
            "https://odata-connector-12.geotab.com/odata/v4/svc/"
            "VehicleKpi_Daily?$search=last_14_day"
        )
        == "https://odata-connector-12.geotab.com/odata/v4/svc/"
    )


def test_discovery_prefers_unified_redirect(monkeypatch):
    mod = _import_router_fresh()
    calls: list[str] = []

    async def _fake_probe(_client, url, _auth):
        calls.append(url)
        if url == mod._ODATA_UNIFIED_SERVER:
            return "https://odata-connector-8.geotab.com/odata/v4/svc/"
        return None

    monkeypatch.setattr(mod, "_probe_server", _fake_probe)

    import asyncio

    result = asyncio.run(mod._find_server())
    assert result == "https://odata-connector-8.geotab.com/odata/v4/svc/"
    assert calls == [mod._ODATA_UNIFIED_SERVER]


def test_vehicle_kpi_aggregator_supports_current_geotab_schema():
    mod = _import_router_fresh()

    vehicles = mod._aggregate_vehicle_kpis(
        [
            {
                "DeviceId": "b11A",
                "Distance_Km": 12.5,
                "DriveDuration_Seconds": 3600,
                "IdleDuration_Seconds": 900,
                "Trip_Count": 2,
                "TotalFuel_Litres": 4.2,
            },
            {
                "DeviceId": "b11A",
                "GPS_Distance_Km": 7.5,
                "DriveDuration_Seconds": 1800,
                "IdleDuration_Seconds": 0,
                "Trip_Count": 1,
            },
        ]
    )

    assert len(vehicles) == 1
    assert vehicles[0]["vehicle_id"] == "b11A"
    assert vehicles[0]["vehicle_name"] == "b11A"
    assert vehicles[0]["distance_miles"] == pytest.approx(12.42742)
    assert vehicles[0]["drive_hours"] == 1.5
    assert vehicles[0]["idle_hours"] == 0.25
    assert vehicles[0]["trips"] == 3
    assert vehicles[0]["fuel_litres"] == 4.2


def test_vehicle_kpi_aggregator_uses_geotab_asset_name_from_metadata():
    mod = _import_router_fresh()
    vehicle_names = mod._vehicle_metadata_name_map(
        [
            {
                "DeviceId": "G8B120F4CFB4",
                "SerialNo": "G8B120F4CFB4",
                "Name": "K1-117",
            }
        ]
    )

    vehicles = mod._aggregate_vehicle_kpis(
        [
            {
                "DeviceId": "G8B120F4CFB4",
                "Distance_Km": 10,
                "DriveDuration_Seconds": 1800,
                "IdleDuration_Seconds": 300,
                "Trip_Count": 1,
            },
            {
                "DeviceId": "G8B120F4CFB4",
                "Distance_Km": 5,
                "DriveDuration_Seconds": 900,
                "IdleDuration_Seconds": 0,
                "Trip_Count": 1,
            },
        ],
        vehicle_names,
    )

    assert len(vehicles) == 1
    assert vehicles[0]["vehicle_id"] == "G8B120F4CFB4"
    assert vehicles[0]["vehicle_name"] == "K1-117"
    assert vehicles[0]["distance_miles"] == pytest.approx(9.320565)
    assert vehicles[0]["drive_hours"] == 0.75
    assert vehicles[0]["idle_hours"] == pytest.approx(0.08333333333333333)
    assert vehicles[0]["trips"] == 2


def test_vehicle_metadata_name_map_uses_unit_aliases():
    mod = _import_router_fresh()

    vehicle_names = mod._vehicle_metadata_name_map(
        [
            {
                "DeviceSerialNumber": "G8B120F4CFB4",
                "VehicleName": "G8B120F4CFB4",
                "UnitNumber": "250",
            }
        ]
    )

    assert vehicle_names["g8b120f4cfb4"] == "250"


def test_trip_summary_converter_returns_miles_only():
    mod = _import_router_fresh()

    rows = mod._convert_trip_summary_rows(
        [
            {
                "VehicleName": "b11A",
                "TotalTrips": 4,
                "TotalDistance_Km": 10,
                "TotalDriveTime_Hours": 1.25,
            }
        ]
    )

    assert rows == [
        {
            "VehicleName": "b11A",
            "TotalTrips": 4,
            "TotalDriveTime_Hours": 1.25,
            "total_distance_miles": pytest.approx(6.21371),
        }
    ]
    assert "TotalDistance_Km" not in rows[0]


def test_fault_trends_returns_empty_when_table_unavailable(monkeypatch):
    mod = _import_router_fresh()

    async def _missing_table(*_args, **_kwargs):
        raise mod.HTTPException(
            404,
            'Data Connector error: {"event":"Metadata","message":"Metadata is Not Found"}',
        )

    monkeypatch.setattr(mod, "_odata_get", _missing_table)

    import asyncio

    result = asyncio.run(mod.fault_trends(days=1))

    assert result["faults"] == []
    assert result["feed_status"] == "table_unavailable"
    assert result["period_days"] == 1


def test_fault_trends_returns_degraded_payload_on_timeout(monkeypatch):
    mod = _import_router_fresh()

    async def _timeout(*_args, **_kwargs):
        raise mod.HTTPException(504, "Data Connector timeout while reading FaultMonitoring_Daily.")

    monkeypatch.setattr(mod, "_odata_get", _timeout)

    import asyncio

    result = asyncio.run(mod.fault_trends(days=14))

    assert result["faults"] == []
    assert result["feed_status"] == "degraded"
    assert result["period_days"] == 14
    assert "timeout" in result["message"].lower()


def test_fault_trends_uses_geotab_asset_name_from_metadata(monkeypatch):
    mod = _import_router_fresh()

    async def _rows(table, *_args, **_kwargs):
        if table == "FaultMonitoring_Daily":
            return [
                {
                    "DeviceId": "G8B120F4CFB4",
                    "FaultCode": "1378",
                    "Count": 2,
                    "Date": "2026-05-02T00:00:00Z",
                }
            ]
        if table == mod._PROBE_TABLE:
            return [
                {
                    "DeviceId": "G8B120F4CFB4",
                    "SerialNo": "G8B120F4CFB4",
                    "Name": "K1-117",
                }
            ]
        return []

    monkeypatch.setattr(mod, "_odata_get", _rows)

    import asyncio

    result = asyncio.run(mod.fault_trends(days=14))

    assert result["feed_status"] == "ok"
    assert result["period_days"] == 14
    assert result["faults"][0]["source_vehicle_id"] == "G8B120F4CFB4"
    assert result["faults"][0]["vehicle_name"] == "K1-117"
    assert result["faults"][0]["fault_code"] == "1378"
    assert result["faults"][0]["count"] == 2
    assert result["faults"][0]["date"] == "2026-05-02"


def test_vehicle_kpis_uses_route_cache(monkeypatch):
    mod = _import_router_fresh()
    call_count = 0

    async def _rows(table, *_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        if table == "VehicleKpi_Daily":
            return [
                {
                    "DeviceId": "G8B120F4CFB4",
                    "Distance_Km": 10,
                    "DriveDuration_Seconds": 3600,
                    "Trip_Count": 1,
                }
            ]
        if table == mod._PROBE_TABLE:
            return [{"DeviceId": "G8B120F4CFB4", "Name": "K1-117"}]
        return []

    monkeypatch.setattr(mod, "_odata_get", _rows)

    import asyncio

    first = asyncio.run(mod.vehicle_kpis(days=7))
    second = asyncio.run(mod.vehicle_kpis(days=7))

    assert first == second
    assert second["feed_status"] == "ok"
    assert second["vehicles"][0]["vehicle_name"] == "K1-117"
    assert call_count == 2


def test_vehicle_kpis_returns_degraded_payload_on_timeout(monkeypatch):
    mod = _import_router_fresh()

    async def _timeout(*_args, **_kwargs):
        raise mod.HTTPException(504, "Data Connector timeout while reading VehicleKpi_Daily.")

    monkeypatch.setattr(mod, "_odata_get", _timeout)

    import asyncio

    result = asyncio.run(mod.vehicle_kpis(days=14))

    assert result["vehicles"] == []
    assert result["summary"]["total_vehicles"] == 0
    assert result["feed_status"] == "degraded"
    assert "timeout" in result["message"].lower()


def test_safety_scores_returns_degraded_payload_on_timeout(monkeypatch):
    mod = _import_router_fresh()

    async def _timeout(*_args, **_kwargs):
        raise mod.HTTPException(504, "Data Connector timeout while reading FleetSafety_Daily.")

    monkeypatch.setattr(mod, "_odata_get", _timeout)

    import asyncio

    result = asyncio.run(mod.safety_scores(days=14))

    assert result["fleet_daily"] == []
    assert result["vehicle_scores"] == []
    assert result["feed_status"] == "degraded"
    assert "timeout" in result["message"].lower()


@pytest.mark.parametrize("route_name", ["vehicle_kpis", "safety_scores", "fault_trends"])
def test_operational_data_connector_routes_return_degraded_payload_on_500(monkeypatch, route_name):
    mod = _import_router_fresh()

    async def _upstream_500(*_args, **_kwargs):
        raise mod.HTTPException(500, "Data Connector error: 500 Internal Server Error")

    monkeypatch.setattr(mod, "_odata_get", _upstream_500)

    import asyncio

    result = asyncio.run(getattr(mod, route_name)(days=14))

    assert result["feed_status"] == "degraded"
    assert result["period_days"] == 14
    assert "500 Internal Server Error" in result["message"]
    if route_name == "vehicle_kpis":
        assert result["vehicles"] == []
        assert result["summary"]["total_vehicles"] == 0
    elif route_name == "safety_scores":
        assert result["fleet_daily"] == []
        assert result["vehicle_scores"] == []
    else:
        assert result["faults"] == []


def test_odata_get_fails_fast_when_request_slots_are_busy(monkeypatch):
    mod = _import_router_fresh()

    async def _server(*_args, **_kwargs):
        return "https://odata-connector-2.geotab.com/odata/v4/svc/"

    monkeypatch.setattr(mod, "_find_server", _server)
    monkeypatch.setattr(mod, "_basic_auth", lambda: ("db/user", "secret"))
    monkeypatch.setattr(mod, "_ODATA_QUEUE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(mod, "_ODATA_REQUEST_SEMAPHORE", mod.asyncio.Semaphore(0))

    import asyncio

    try:
        asyncio.run(mod._odata_get("VehicleKpi_Daily"))
    except mod.HTTPException as exc:
        assert exc.status_code == 503
        assert "busy" in exc.detail
    else:
        raise AssertionError("_odata_get should fail fast when all slots are busy")


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
    assert mod._ODATA_DISCOVERY_SERVERS[0] == "https://data-connector.geotab.com/odata/v4/svc/"
    assert len(mod._ODATA_SERVERS) == 15
    assert mod._ODATA_SERVERS[0].startswith("https://odata-connector-1.geotab.com/")
    assert mod._ODATA_SERVERS[-1].startswith("https://odata-connector-15.geotab.com/")
