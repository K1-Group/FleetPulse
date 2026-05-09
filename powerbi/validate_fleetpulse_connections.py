#!/usr/bin/env python3
"""Validate FleetPulse Power BI read-only endpoint health."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


BASE_URL = "https://k1-fleetpulse.azurewebsites.net"


@dataclass(frozen=True)
class Endpoint:
    name: str
    path: str
    expect_list: bool
    require_non_empty: bool = True


ENDPOINTS = [
    Endpoint("overview", "/api/powerbi/overview", True),
    Endpoint("locations", "/api/powerbi/locations", True, require_non_empty=False),
    Endpoint("vehicles", "/api/powerbi/vehicles", True),
    Endpoint("safety_scores", "/api/powerbi/safety-scores?days=7", True),
    Endpoint("fleetpulse_snapshot", "/api/powerbi/fleetpulse-snapshot?days=7", False),
]


def fetch_json(url: str) -> tuple[int, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            status = response.getcode()
            payload = json.loads(response.read().decode("utf-8"))
            return status, payload
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, {"error": body[:500]}


def validate_list_rows(endpoint: Endpoint, payload: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": endpoint.name,
        "row_count": 0,
        "ok": False,
        "schema": [],
    }
    if not isinstance(payload, list):
        result["error"] = "payload_not_list"
        return result

    result["row_count"] = len(payload)
    if endpoint.require_non_empty and not payload:
        result["error"] = "empty_payload"
        return result

    first_row = payload[0] if payload else {}
    if isinstance(first_row, dict):
        result["schema"] = sorted(first_row.keys())
        if first_row.get("projection_mode") != "read_only":
            result["error"] = "projection_mode_not_read_only"
            return result
        if first_row.get("source_authority") != "Geotab":
            result["error"] = "source_authority_not_geotab"
            return result

    result["ok"] = True
    return result


def validate_snapshot(payload: Any, observed_counts: dict[str, int]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": "fleetpulse_snapshot",
        "ok": False,
        "row_counts": {},
    }
    if not isinstance(payload, dict):
        result["error"] = "payload_not_object"
        return result
    if payload.get("projection_mode") != "read_only":
        result["error"] = "projection_mode_not_read_only"
        return result
    if payload.get("source_authority") != "Geotab":
        result["error"] = "source_authority_not_geotab"
        return result

    row_counts = payload.get("row_counts") or {}
    result["row_counts"] = row_counts
    expected = {
        "overview": observed_counts.get("overview"),
        "locations": observed_counts.get("locations"),
        "vehicles": observed_counts.get("vehicles"),
        "safety_scores": observed_counts.get("safety_scores"),
    }
    mismatches = {
        name: {"snapshot": row_counts.get(name), "endpoint": count}
        for name, count in expected.items()
        if row_counts.get(name) != count
    }
    if mismatches:
        result["error"] = "snapshot_count_mismatch"
        result["mismatches"] = mismatches
        return result

    result["ok"] = True
    return result


def main() -> int:
    observed_counts: dict[str, int] = {}
    validations: list[dict[str, Any]] = []

    for endpoint in ENDPOINTS:
        url = BASE_URL + endpoint.path
        status, payload = fetch_json(url)
        if status != 200:
            validations.append(
                {
                    "name": endpoint.name,
                    "ok": False,
                    "status": status,
                    "error": "http_error",
                    "url": url,
                }
            )
            continue

        if endpoint.expect_list:
            result = validate_list_rows(endpoint, payload)
            observed_counts[endpoint.name] = int(result.get("row_count", 0))
        else:
            result = validate_snapshot(payload, observed_counts)
        result["status"] = status
        result["url"] = url
        validations.append(result)

    report = {
        "base_url": BASE_URL,
        "ok": all(item.get("ok") for item in validations),
        "validations": validations,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

