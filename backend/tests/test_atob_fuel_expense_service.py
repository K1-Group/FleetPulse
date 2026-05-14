"""Tests for AtoB manual fuel expense imports."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services.atob_fuel_expense_service import (  # noqa: E402
    AtoBFuelExpenseStateStore,
    get_atob_fuel_summary,
    import_atob_fuel_expenses,
)


def _sample_csv(transaction_id: str = "A-100") -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    return (
        "Transaction ID,Transaction Date,Merchant,Amount,Gallons,Vehicle,Driver,Card Number\n"
        f"{transaction_id},{today},Pilot,$123.45,31.25,5439 Idealease -HDS DFW,Jane Driver,4111111111111234\n"
    )


def test_atob_import_is_idempotent_and_redacts_card_data(tmp_path):
    store = AtoBFuelExpenseStateStore(tmp_path / "atob-state.json")

    first = import_atob_fuel_expenses(_sample_csv(), filename="atob.csv", store=store)
    second = import_atob_fuel_expenses(_sample_csv(), filename="atob.csv", store=store)
    summary = get_atob_fuel_summary(days=30, store=store)
    record = store.records()[0]

    assert first.imported_count == 1
    assert first.duplicate_count == 0
    assert second.imported_count == 0
    assert second.duplicate_count == 1
    assert summary["transaction_count"] == 1
    assert summary["total_cost"] == 123.45
    assert summary["total_gallons"] == 31.25
    assert record["card_last4"] == "1234"
    assert record["raw"]["Card Number"] == "****1234"


def test_atob_dry_run_does_not_write_state(tmp_path):
    state_path = tmp_path / "atob-state.json"
    store = AtoBFuelExpenseStateStore(state_path)

    result = import_atob_fuel_expenses(
        _sample_csv("A-200"),
        filename="atob.csv",
        dry_run=True,
        store=store,
    )

    assert result.imported_count == 1
    assert not state_path.exists()


def test_atob_import_reports_invalid_rows(tmp_path):
    store = AtoBFuelExpenseStateStore(tmp_path / "atob-state.json")
    content = "Transaction ID,Transaction Date,Amount\nA-300,,123.45\n"

    result = import_atob_fuel_expenses(content, filename="bad.csv", store=store)

    assert result.status == "invalid"
    assert result.imported_count == 0
    assert result.invalid_count == 1
    assert "missing transaction date" in result.errors[0]
