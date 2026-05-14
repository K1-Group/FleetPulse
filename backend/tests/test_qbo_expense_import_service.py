"""Tests for manual QBO expense import projections."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services.qbo_expense_import_service import (  # noqa: E402
    QboExpenseStateStore,
    get_qbo_expense_summary,
    import_qbo_expenses,
)


def test_qbo_expense_import_dedupes_and_summarizes_source_rows(tmp_path):
    store = QboExpenseStateStore(path=tmp_path / "qbo-expenses.json")
    content = "\n".join(
        [
            "Date,Transaction Type,Num,Name,Account,Amount,Memo",
            "01/05/2026,Expense,1001,Progressive,Commercial Auto Insurance,$500.00,policy",
            "01/06/2026,Expense,1002,Repair Shop,Repairs and Maintenance,$125.25,unit repair",
            "01/07/2026,Expense,1003,AtoB,Fuel Expense,$999.00,fuel card",
        ]
    )

    first = import_qbo_expenses(
        content,
        filename="qbo-expenses.csv",
        period_start="2026-01-01",
        period_end="2026-01-31",
        store=store,
    )
    second = import_qbo_expenses(content, filename="qbo-expenses.csv", store=store)
    summary = get_qbo_expense_summary(days=370, store=store)

    assert first.imported_count == 3
    assert first.summary["insurance_total"] == 500.0
    assert first.summary["other_expense_total"] == 125.25
    assert first.summary["excluded_expense_count"] == 1
    assert second.imported_count == 0
    assert second.duplicate_count == 3
    assert summary["coverage_start"] == "2026-01-01"
    assert summary["coverage_end"] == "2026-01-31"
    assert summary["included_expense_total"] == 625.25


def test_qbo_expense_import_skips_non_transaction_rows(tmp_path):
    store = QboExpenseStateStore(path=tmp_path / "qbo-expenses.json")
    content = "\n".join(
        [
            "Date,Transaction Type,Name,Account,Amount",
            ",,,,,",
            ",Total Insurance,,,500.00",
            "02/01/2026,Expense,Carrier,Carrier & Factoring Company,1000.00",
            "02/02/2026,Expense,Insurance Co,Insurance,250.00",
        ]
    )

    result = import_qbo_expenses(content, filename="qbo.csv", store=store)

    assert result.imported_count == 2
    assert result.invalid_count == 1
    assert result.summary["insurance_total"] == 250.0
    assert result.summary["excluded_expense_count"] == 1
