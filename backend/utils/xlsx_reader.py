"""Small XLSX row reader for read-only local artifacts.

This intentionally avoids workbook-writing dependencies. It only extracts cell
values from existing `.xlsx` sheets so FleetPulse can project approved artifacts
without becoming an authoring or source-of-truth system.
"""

from __future__ import annotations

import posixpath
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET


MAIN_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def read_xlsx_sheet_rows(path: str | Path, sheet_name: str) -> list[list[str]]:
    """Return rows from one sheet in an XLSX workbook as cached display values."""

    workbook_path = Path(path)
    with ZipFile(workbook_path) as archive:
        shared_strings = _shared_strings(archive)
        worksheet_path = _worksheet_path(archive, sheet_name)
        root = ET.fromstring(archive.read(worksheet_path))

    rows: list[list[str]] = []
    for row in root.findall(".//a:sheetData/a:row", MAIN_NS):
        values: list[str] = []
        for cell in row.findall("a:c", MAIN_NS):
            cell_index = _column_index(cell.attrib.get("r", "A1"))
            while len(values) < cell_index:
                values.append("")
            values.append(_cell_value(cell, shared_strings))
        while values and values[-1] == "":
            values.pop()
        rows.append(values)
    return rows


def _shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall("a:si", MAIN_NS):
        values.append("".join(text.text or "" for text in item.findall(".//a:t", MAIN_NS)))
    return values


def _worksheet_path(archive: ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        relationship.attrib["Id"]: relationship.attrib["Target"]
        for relationship in relationships.findall("r:Relationship", REL_NS)
    }

    for sheet in workbook.findall("a:sheets/a:sheet", MAIN_NS):
        if sheet.attrib.get("name") != sheet_name:
            continue
        relationship_id = sheet.attrib[f"{{{OFFICE_REL_NS}}}id"]
        target = targets[relationship_id].lstrip("/")
        if target.startswith("xl/"):
            return target
        return posixpath.normpath(posixpath.join("xl", target))
    raise KeyError(f"Sheet not found: {sheet_name}")


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    value_type = cell.attrib.get("t")
    if value_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//a:t", MAIN_NS))

    value = cell.find("a:v", MAIN_NS)
    raw = value.text if value is not None and value.text is not None else ""
    if value_type == "s" and raw:
        return shared_strings[int(raw)]
    return raw


def _column_index(cell_ref: str) -> int:
    index = 0
    for char in "".join(ch for ch in cell_ref if ch.isalpha()):
        index = index * 26 + ord(char.upper()) - 64
    return max(index - 1, 0)
