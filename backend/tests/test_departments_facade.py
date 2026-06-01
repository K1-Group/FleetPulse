"""Compatibility tests for the department-folder restructure.

These tests assert that:
1. Each `backend/departments/<dept>` package imports cleanly.
2. Each department's router/service facade exposes the expected attributes
   AND that those objects come from the existing `routers.*` / `services.*`
   modules (so we have not accidentally introduced duplicate logic).
3. Existing FastAPI routes still mount under their original prefixes after
   importing the department facades.
4. New source-system integration wrappers (qbo, geotab, atob_fuel,
   grasshopper) import cleanly and re-export from the central modules.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


DEPARTMENT_MODULES = [
    "departments.executive",
    "departments.finance",
    "departments.operations",
    "departments.fleet_compliance",
    "departments.people_systems",
    "departments.revenue",
    "departments.hr_recruiting",
]


EXPECTED_SEAT_IDS = {
    "departments.executive": "executive_command",
    "departments.finance": "finance_controller",
    "departments.operations": "operations_manager",
    "departments.fleet_compliance": "fleet_compliance_manager",
    "departments.people_systems": "people_systems_manager",
    "departments.revenue": "revenue_manager",
    "departments.hr_recruiting": "people_systems_manager",
}


@pytest.mark.parametrize("mod_path", DEPARTMENT_MODULES)
def test_department_package_imports(mod_path: str) -> None:
    mod = importlib.import_module(mod_path)
    assert hasattr(mod, "router"), f"{mod_path} missing router facade"
    assert hasattr(mod, "service"), f"{mod_path} missing service facade"
    assert hasattr(mod, "contracts"), f"{mod_path} missing contracts module"


@pytest.mark.parametrize("mod_path", DEPARTMENT_MODULES)
def test_department_router_facade_specs(mod_path: str) -> None:
    mod = importlib.import_module(f"{mod_path}.router")
    assert hasattr(mod, "ROUTERS"), f"{mod_path}.router missing ROUTERS"
    assert isinstance(mod.ROUTERS, list) and mod.ROUTERS, (
        f"{mod_path}.router ROUTERS must be non-empty"
    )
    for entry in mod.ROUTERS:
        assert len(entry) == 4, "Each ROUTERS entry must be (name, prefix, tags, router)"
        name, prefix, tags, router = entry
        assert isinstance(name, str) and name
        assert prefix.startswith("/api/"), f"{mod_path} router {name} prefix should be /api/*"
        assert isinstance(tags, list) and tags
        assert router is not None


@pytest.mark.parametrize("mod_path", DEPARTMENT_MODULES)
def test_department_router_objects_are_central(mod_path: str) -> None:
    """Facades must re-export routers from `routers.*` — no duplicate routers."""
    mod = importlib.import_module(f"{mod_path}.router")
    for name, _prefix, _tags, router in mod.ROUTERS:
        original = importlib.import_module(f"routers.{name}")
        assert router is original.router, (
            f"{mod_path} re-exported router {name!r} is not identical to routers.{name}.router; "
            "facade must not own its own router instance"
        )


@pytest.mark.parametrize("mod_path", DEPARTMENT_MODULES)
def test_department_contracts_carry_metadata(mod_path: str) -> None:
    mod = importlib.import_module(f"{mod_path}.contracts")
    assert hasattr(mod, "DEPARTMENT_ID")
    assert hasattr(mod, "SEAT_ID")
    assert hasattr(mod, "DASHBOARD_TABS")
    assert mod.SEAT_ID == EXPECTED_SEAT_IDS[mod_path], (
        f"{mod_path}.contracts.SEAT_ID mismatch"
    )
    assert isinstance(mod.DASHBOARD_TABS, list) and mod.DASHBOARD_TABS


def test_app_still_mounts_existing_prefixes() -> None:
    """Ensure the FastAPI app continues to expose its original routes after
    the restructure (sanity check that we didn't break router loading)."""
    import app as app_module  # type: ignore

    paths = {route.path for route in app_module.app.routes}
    expected_prefixes = [
        "/api/dashboard",
        "/api/control-tower",
        "/api/maintenance",
        "/api/fuel",
        "/api/driver-workforce",
        "/api/hr-recruiting",
        "/api/lane-stability",
        "/api/operating-system",
    ]
    for prefix in expected_prefixes:
        assert any(p.startswith(prefix) for p in paths), (
            f"No mounted route under prefix {prefix!r}"
        )


def test_integration_qbo_reexports_central_services() -> None:
    import integrations.qbo as qbo
    import services.qbo_financial_snapshot_service as snapshot
    import services.qbo_financial_feed_import_service as feed
    import services.qbo_expense_import_service as expense

    assert qbo.financial_snapshot is snapshot
    assert qbo.financial_feed_import is feed
    assert qbo.expense_import is expense


def test_integration_atob_fuel_reexports_central_services() -> None:
    import integrations.atob_fuel as atob
    import services.atob_fuel_expense_service as expense
    import services.atob_sharepoint_sync_service as sp_sync

    assert atob.expense is expense
    assert atob.sharepoint_sync is sp_sync


def test_integration_geotab_reexports_central_client() -> None:
    import integrations.geotab as geotab_pkg
    import geotab_client

    assert geotab_pkg.client is geotab_client


def test_integration_grasshopper_placeholder_imports() -> None:
    # Placeholder package — must import without error and expose no clients yet.
    import integrations.grasshopper as grasshopper

    assert grasshopper.__all__ == []
