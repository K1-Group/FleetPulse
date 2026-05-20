"""Tests for read-only QuickBooks AP/AR and K1L expense projections."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services.qbo_financial_snapshot_service import (  # noqa: E402
    QboFinancialConfig,
    get_qbo_financial_snapshot,
    load_qbo_k1l_expense_rows,
)


def test_qbo_financial_snapshot_summarizes_ap_ar_and_k1l_expenses(tmp_path):
    feed_path = tmp_path / "qbo-financial.json"
    feed_path.write_text(
        json.dumps(
            {
                "coverage_start": "2026-01-01",
                "coverage_end": "2026-05-19",
                "accounts_payable": [
                    {
                        "Type": "Bill",
                        "Due Date": "2026-05-01",
                        "Open Balance": "1,200.00",
                        "Vendor": "Repair Shop",
                    },
                    {
                        "Type": "Bill",
                        "Due Date": "2026-05-30",
                        "Open Balance": "300.00",
                        "Vendor": "Parts Vendor",
                    },
                ],
                "accounts_receivable": [
                    {
                        "Type": "Invoice",
                        "Due Date": "2026-05-10",
                        "Open Balance": "1,000.00",
                        "Customer": "Customer A",
                    },
                    {
                        "Type": "Invoice",
                        "Due Date": "2026-03-01",
                        "Open Balance": "250.00",
                        "Customer": "Customer B",
                    },
                ],
                "expenses": [
                    {
                        "Date": "2026-05-04",
                        "Account": "Repairs and Maintenance",
                        "Amount": "100.00",
                        "Class": "K1 Logistics Inc",
                    },
                    {
                        "Date": "2026-05-05",
                        "Account": "Office Expense",
                        "Amount": "40.00",
                        "Class": "K1 Group LLC",
                    },
                    {
                        "Date": "2026-05-06",
                        "Account": "Fuel Expense",
                        "Amount": "999.00",
                        "Class": "K1 Logistics Inc",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = get_qbo_financial_snapshot(
        start="2026-05-01",
        end="2026-05-19",
        config=QboFinancialConfig(feed_path=str(feed_path)),
        today=date(2026, 5, 19),
    )

    assert snapshot["status"] == "healthy"
    assert snapshot["accounts_payable"]["pending_amount"] == 1500.0
    assert snapshot["accounts_payable"]["pending_bills"] == 2
    assert snapshot["accounts_payable"]["overdue_amount"] == 1200.0
    assert snapshot["accounts_payable"]["overdue_count"] == 1
    ar = {bucket["bucket"]: bucket for bucket in snapshot["accounts_receivable"]}
    assert ar["0-30"]["amount"] == 1000.0
    assert ar["61-90"]["amount"] == 250.0
    assert snapshot["expense_summary"]["k1l_expense_total"] == 100.0
    assert snapshot["expense_summary"]["k1l_expense_count"] == 1


def test_qbo_financial_snapshot_missing_config_is_explicit():
    snapshot = get_qbo_financial_snapshot(config=QboFinancialConfig())

    assert snapshot["status"] == "awaiting_feed"
    assert "FLEETPULSE_QBO_FINANCIAL_FEED_URL" in snapshot["missing_config"]
    assert snapshot["accounts_payable"]["pending_amount"] is None
    assert snapshot["cash_flow"]["k1l_expense_total"] is None


def test_qbo_expense_rows_for_operating_cost_are_k1l_only(tmp_path):
    feed_path = tmp_path / "qbo-financial.json"
    feed_path.write_text(
        json.dumps(
            {
                "expenses": [
                    {
                        "Date": "2026-05-04",
                        "Account": "Commercial Auto Insurance",
                        "Amount": "50.00",
                        "Class": "K1 Logistics Inc",
                    },
                    {
                        "Date": "2026-05-05",
                        "Account": "Repairs and Maintenance",
                        "Amount": "75.00",
                        "Class": "K1 Logistics Inc",
                    },
                    {
                        "Date": "2026-05-05",
                        "Account": "Repairs and Maintenance",
                        "Amount": "30.00",
                        "Class": "K1 Group LLC",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    rows, metadata = load_qbo_k1l_expense_rows(
        config=QboFinancialConfig(feed_path=str(feed_path)),
        start="2026-05-04",
        end="2026-05-10",
    )

    assert metadata["source_status"] == "healthy"
    assert [row["Amount"] for row in rows] == [50.0, 75.0]
    assert rows[0]["qbo_expense_bucket"] == "insurance"
    assert rows[1]["qbo_expense_bucket"] == "other"
