"""Tests for the read-only unified route/LH scorecard projection."""

from __future__ import annotations

import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape


BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services.unified_route_lh_scorecard_service import (  # noqa: E402
    UnifiedRouteLHScorecardConfig,
    get_unified_route_lh_scorecard,
)


def _column_name(index: int) -> str:
    value = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        value = chr(65 + remainder) + value
    return value


def _worksheet_xml(rows: list[list[str]]) -> str:
    row_xml: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row):
            if value == "":
                continue
            ref = f"{_column_name(col_index)}{row_index}"
            cells.append(
                f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
            )
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(row_xml)}</sheetData>'
        "</worksheet>"
    )


def _write_workbook(path: Path) -> None:
    sheets = {
        "Dashboard": [
            ["Unified Route/LH Scorecard"],
            ["Scorecard Units", "", "Local Routes", "", "LH Lanes", "", "Company Avg Revenue/Hr", "", "Missed Hours"],
            ["2", "", "1", "", "1", "", "100", "", "12.5"],
            ["Missed Hour Revenue", "", "Avg Stability", "", "Avg On-Time", "", "Avg Tech", "", "Safety"],
            ["1250", "", "0.9", "", "0.95", "", "0.8", "", "Needs Geotab"],
        ],
        "Unified Scorecard": [
            ["Unified Scorecard"],
            ["One row per local route or LH lane"],
            [
                "Work Type",
                "Entity",
                "Route/LH",
                "Service",
                "Customer / Relationship",
                "Primary Driver",
                "Active Days",
                "Orders / Stops",
                "Current Sales",
                "Avg Sales/Day",
                "Missed Hours",
                "Company Avg Revenue/Hr",
                "Missed Hour Revenue",
                "Stability %",
                "On-Time Performance %",
                "Safety %",
                "Tech Performance %",
                "Attendance %",
                "Route/LH Gross Margin %",
                "Relationship Band",
                "Risk Management Band",
                "Sales / Relationship Action",
                "Capacity Status",
                "Source Boundary",
            ],
            [
                "Local Route",
                "K1 Logistics Inc",
                "DFW 001",
                "Local Route Mix",
                "Hackbarth",
                "4",
                "5",
                "10",
                "5000",
                "1000",
                "12.5",
                "100",
                "1250",
                "0.9",
                "0.95",
                "Not scored",
                "0.8",
                "Not scored",
                "0.7",
                "Sell Capacity",
                "Action",
                "Sell available paid capacity with service guardrails",
                "Capacity available",
                "Read-side planning artifact only",
            ],
            [
                "LH Lane",
                "K1 Group LLC",
                "DHL DFW>SCF OKC",
                "LH",
                "Send It Logistics",
                "315",
                "5",
                "5",
                "4905",
                "981",
                "0",
                "100",
                "0",
                "0.85",
                "0.9",
                "Not scored",
                "1",
                "Not scored",
                "0.3",
                "Maintain",
                "Medium",
                "Maintain current service plan",
                "No route capacity window",
                "Read-side planning artifact only",
            ],
        ],
        "Metric Definitions": [
            ["Metric Definitions"],
            ["Metric", "Definition"],
            ["Source", "/tmp/ReviewOrders.xlsx"],
            ["Source Boundary", "Read-side planning artifact only. Xcelerator remains operations/financial source; Geotab remains safety source."],
            ["Safety Source Audit", "FleetPulse Geotab safety service returned 0 live rows with demo mode off"],
        ],
    }
    workbook_sheets = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheets, start=1)
    )
    relationships = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, len(sheets) + 1)
    )
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<sheets>{workbook_sheets}</sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{relationships}</Relationships>",
        )
        for index, rows in enumerate(sheets.values(), start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _worksheet_xml(rows))


def test_unified_route_lh_scorecard_loads_workbook_values(tmp_path):
    workbook = tmp_path / "K1_Unified_Route_LH_Scorecard_WE_2026-05-23.xlsx"
    _write_workbook(workbook)

    payload = get_unified_route_lh_scorecard(
        UnifiedRouteLHScorecardConfig(workbook_path=workbook)
    )

    assert payload["feed_status"] == "healthy"
    assert payload["period_end"] == "2026-05-23"
    assert payload["projection_mode"] == "read_only"
    assert payload["summary"]["scorecard_units"] == 2
    assert payload["summary"]["local_routes"] == 1
    assert payload["summary"]["lh_lanes"] == 1
    assert payload["summary"]["missed_hour_revenue"] == 1250.0
    assert payload["summary"]["local_missed_hour_revenue"] == 1250.0
    assert payload["summary"]["lh_missed_hour_revenue"] == 0.0
    assert payload["summary"]["safety_status"] == "Needs Geotab"
    assert payload["items"][0]["route_lh"] == "DFW 001"
    assert payload["items"][0]["sales_relationship_action"] == "Sell available paid capacity with service guardrails"
    assert payload["action_summary"][0]["missed_hour_revenue"] == 1250.0
    assert payload["source_notes"][1]["metric"] == "Source Boundary"
    assert payload["source_boundaries"][2]["system"] == "FleetPulse"


def test_unified_route_lh_scorecard_missing_file_is_awaiting_feed(tmp_path):
    payload = get_unified_route_lh_scorecard(
        UnifiedRouteLHScorecardConfig(workbook_path=tmp_path / "missing.xlsx")
    )

    assert payload["feed_status"] == "awaiting_feed"
    assert payload["items"] == []
    assert payload["summary"]["missed_hour_revenue"] == 0.0
