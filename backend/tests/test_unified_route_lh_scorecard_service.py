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


def _write_workbook(
    path: Path,
    route_missed_hours: str = "12.5",
    route_missed_revenue: str = "1250",
    include_gap_detail: bool = True,
) -> None:
    sheets = {
        "Dashboard": [
            ["Unified Route/LH Scorecard"],
            ["Scorecard Units", "", "Local Routes", "", "LH Lanes", "", "Company Avg Revenue/Hr", "", "Missed Hours"],
            ["2", "", "1", "", "1", "", "100", "", route_missed_hours],
            ["Missed Hour Revenue", "", "Avg Stability", "", "Avg On-Time", "", "Avg Tech", "", "Safety"],
            [route_missed_revenue, "", "0.9", "", "0.95", "", "0.8", "", "Needs Geotab"],
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
                route_missed_hours,
                "100",
                route_missed_revenue,
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
    }
    if include_gap_detail:
        sheets["Gap Detail"] = [
            ["Gap Detail"],
            ["Exact local route capacity windows used for missed-hour revenue"],
            [],
            [
                "Entity",
                "Route",
                "Date",
                "Gap Type",
                "Gap From",
                "Gap To",
                "Gap Window",
                "Missed Hours",
                "Company Avg Revenue/Hr",
                "Missed Hour Revenue",
                "Paid Window Basis",
            ],
            [
                "K1 Logistics Inc",
                "DFW 002",
                "2026-05-18",
                "Between stops",
                "46160.3125",
                "46160.91666666666",
                "5/18 07:30 AM to 10:00 PM",
                "14.5",
                "85.59999999999999",
                "1241.19",
                "12h shift target",
            ],
            [
                "K1 Logistics Inc",
                "DFW 002",
                "2026-05-19",
                "Between stops",
                "46161.3125",
                "46161.91666666666",
                "5/19 07:30 AM to 10:00 PM",
                "14.5",
                "85.59999999999999",
                "1241.19",
                "12h shift target",
            ],
            [
                "K1 Logistics Inc",
                "DFW 001",
                "2026-05-17",
                "Full paid window",
                "46159.72916666666",
                "46160.3125",
                "5/17 05:30 PM to 5/18 07:30 AM",
                "14",
                "85.59999999999999",
                "1198.39",
                "Paid ticket",
            ],
        ]
    sheets["Metric Definitions"] = [
        ["Metric Definitions"],
        ["Metric", "Definition"],
        ["Source", "/tmp/ReviewOrders.xlsx"],
        ["Source Boundary", "Read-side planning artifact only. Xcelerator remains operations/financial source; Geotab remains safety source."],
        ["Safety Source Audit", "FleetPulse Geotab safety service returned 0 live rows with demo mode off"],
    ]
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
    assert payload["comparison"]["status"] == "awaiting_prior_scorecard"
    assert payload["gap_detail"]["status"] == "healthy"
    assert payload["gap_detail"]["total_windows"] == 3
    assert payload["gap_detail"]["total_missed_hour_revenue"] == 3680.77
    assert payload["gap_detail"]["windows"][0]["route"] == "DFW 002"
    assert payload["gap_detail"]["windows"][0]["gap_window"] == "5/18 07:30 AM to 10:00 PM"
    assert payload["gap_detail"]["route_summary"][0]["route"] == "DFW 002"
    assert payload["gap_detail"]["route_summary"][0]["window_count"] == 2
    assert payload["source_notes"][1]["metric"] == "Source Boundary"
    assert payload["source_boundaries"][2]["system"] == "FleetPulse"


def test_unified_route_lh_scorecard_compares_approved_prior_workbook(tmp_path):
    workbook = tmp_path / "K1_Unified_Route_LH_Scorecard_WE_2026-05-23.xlsx"
    prior = tmp_path / "K1_Unified_Route_LH_Scorecard_WE_2026-05-16.xlsx"
    _write_workbook(workbook, route_missed_hours="12.5", route_missed_revenue="1250")
    _write_workbook(prior, route_missed_hours="10", route_missed_revenue="1000")

    payload = get_unified_route_lh_scorecard(
        UnifiedRouteLHScorecardConfig(workbook_path=workbook, prior_workbook_path=prior)
    )

    comparison = payload["comparison"]
    assert comparison["status"] == "healthy"
    assert comparison["period_end_current"] == "2026-05-23"
    assert comparison["period_end_prior"] == "2026-05-16"
    revenue_metric = next(metric for metric in comparison["metrics"] if metric["key"] == "missed_hour_revenue")
    assert revenue_metric["prior"] == 1000.0
    assert revenue_metric["current"] == 1250.0
    assert revenue_metric["delta"] == 250.0
    assert revenue_metric["delta_pct"] == 0.25
    assert revenue_metric["direction"] == "up"


def test_unified_route_lh_scorecard_missing_gap_detail_stays_read_only(tmp_path):
    workbook = tmp_path / "K1_Unified_Route_LH_Scorecard_WE_2026-05-23.xlsx"
    _write_workbook(workbook, include_gap_detail=False)

    payload = get_unified_route_lh_scorecard(
        UnifiedRouteLHScorecardConfig(workbook_path=workbook)
    )

    assert payload["feed_status"] == "healthy"
    assert payload["gap_detail"]["status"] == "missing"
    assert payload["gap_detail"]["total_windows"] == 0
    assert payload["gap_detail"]["windows"] == []


def test_unified_route_lh_scorecard_missing_file_is_awaiting_feed(tmp_path):
    payload = get_unified_route_lh_scorecard(
        UnifiedRouteLHScorecardConfig(workbook_path=tmp_path / "missing.xlsx")
    )

    assert payload["feed_status"] == "awaiting_feed"
    assert payload["items"] == []
    assert payload["summary"]["missed_hour_revenue"] == 0.0
    assert payload["comparison"]["status"] == "awaiting_prior_scorecard"
    assert payload["gap_detail"]["status"] == "awaiting_feed"
