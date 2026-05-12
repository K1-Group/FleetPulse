#!/usr/bin/env python3
"""Publish FleetPulse live data into a Power BI workspace.

The script uses Azure CLI for delegated auth by default and never prints tokens.
It creates or refreshes a Push semantic model, creates a dashboard shell,
publishes a native PBIR report, and can optionally clone an existing FleetPulse
report onto the new semantic model.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from base64 import b64encode
from typing import Any


POWERBI_API = "https://api.powerbi.com/v1.0/myorg"
FLEETPULSE_BASE_URL = os.getenv("FLEETPULSE_BASE_URL", "https://k1-fleetpulse.azurewebsites.net")
WORKSPACE_ID = os.getenv("POWERBI_WORKSPACE_ID", "b801f80d-5303-4121-abd1-1163639ef58b")
WORKSPACE_NAME = os.getenv("POWERBI_WORKSPACE_NAME", "K1 Operations Hub")
DATASET_NAME = os.getenv("POWERBI_DATASET_NAME", "FleetPulse Live Operations")
DASHBOARD_NAME = os.getenv("POWERBI_DASHBOARD_NAME", "FleetPulse Live Operations Dashboard")
CLONE_REPORT_NAME = os.getenv("POWERBI_CLONE_REPORT_NAME", "FleetPulse Live Operations Report")
SOURCE_REPORT_ID = os.getenv("POWERBI_SOURCE_REPORT_ID", "11418278-aee5-4d4a-9379-f3a51a84794f")
NATIVE_REPORT_NAME = os.getenv("POWERBI_NATIVE_REPORT_NAME", "FleetPulse Live Operations Native Report")
ENABLE_CLONE = os.getenv("POWERBI_ENABLE_CLONE", "false").strip().lower() == "true"


TABLE_ENDPOINTS = {
    "FleetPulseOverview": "/api/powerbi/overview",
    "FleetPulseLocations": "/api/powerbi/locations",
    "FleetPulseVehicles": "/api/powerbi/vehicles",
    "FleetPulseSafetyScores": "/api/powerbi/safety-scores?days=7",
    "LaneStabilityCompany": "/api/powerbi/lane-stability/company?days=7",
    "LaneStabilityByService": "/api/powerbi/lane-stability/by-service?days=7",
    "LaneStabilityLanes": "/api/powerbi/lane-stability/lanes?days=7",
    "LaneStabilityRoutes": "/api/powerbi/lane-stability/routes?days=7",
    "LaneStabilityDaily": "/api/powerbi/lane-stability/daily?days=7",
    "LaneStabilityTrend": "/api/powerbi/lane-stability/trend?days=7",
}

TABLE_SCHEMAS: dict[str, list[dict[str, str]]] = {
    "FleetPulseOverview": [
        {"name": "total_vehicles", "dataType": "Int64"},
        {"name": "active", "dataType": "Int64"},
        {"name": "idle", "dataType": "Int64"},
        {"name": "parked", "dataType": "Int64"},
        {"name": "offline", "dataType": "Int64"},
        {"name": "total_trips_today", "dataType": "Int64"},
        {"name": "total_stops_today", "dataType": "Int64"},
        {"name": "total_distance_miles", "dataType": "Double"},
        {"name": "avg_trip_duration_min", "dataType": "Double"},
        {"name": "avg_trip_duration_hours", "dataType": "Double"},
        {"name": "avg_trip_distance_miles", "dataType": "Double"},
        {"name": "target_trip_duration_hours", "dataType": "Double"},
        {"name": "trips_meeting_target", "dataType": "Int64"},
        {"name": "trips_under_target", "dataType": "Int64"},
        {"name": "trip_definition", "dataType": "String"},
        {"name": "connection_name", "dataType": "String"},
        {"name": "exported_at", "dataType": "DateTime"},
        {"name": "source_system", "dataType": "String"},
        {"name": "source_authority", "dataType": "String"},
        {"name": "projection_mode", "dataType": "String"},
    ],
    "FleetPulseLocations": [
        {"name": "name", "dataType": "String"},
        {"name": "address", "dataType": "String"},
        {"name": "latitude", "dataType": "Double"},
        {"name": "longitude", "dataType": "Double"},
        {"name": "vehicle_count", "dataType": "Int64"},
        {"name": "active", "dataType": "Int64"},
        {"name": "safety_score", "dataType": "Double"},
        {"name": "connection_name", "dataType": "String"},
        {"name": "exported_at", "dataType": "DateTime"},
        {"name": "source_system", "dataType": "String"},
        {"name": "source_authority", "dataType": "String"},
        {"name": "projection_mode", "dataType": "String"},
    ],
    "FleetPulseVehicles": [
        {"name": "id", "dataType": "String"},
        {"name": "name", "dataType": "String"},
        {"name": "status", "dataType": "String"},
        {"name": "location_name", "dataType": "String"},
        {"name": "odometer_km", "dataType": "Double"},
        {"name": "last_contact", "dataType": "DateTime"},
        {"name": "latitude", "dataType": "Double"},
        {"name": "longitude", "dataType": "Double"},
        {"name": "bearing", "dataType": "Double"},
        {"name": "speed", "dataType": "Double"},
        {"name": "connection_name", "dataType": "String"},
        {"name": "exported_at", "dataType": "DateTime"},
        {"name": "source_system", "dataType": "String"},
        {"name": "source_authority", "dataType": "String"},
        {"name": "projection_mode", "dataType": "String"},
    ],
    "FleetPulseSafetyScores": [
        {"name": "vehicle_id", "dataType": "String"},
        {"name": "vehicle_name", "dataType": "String"},
        {"name": "score", "dataType": "Double"},
        {"name": "trend", "dataType": "String"},
        {"name": "event_count", "dataType": "Int64"},
        {"name": "speeding_events", "dataType": "Int64"},
        {"name": "harsh_braking_events", "dataType": "Int64"},
        {"name": "harsh_acceleration_events", "dataType": "Int64"},
        {"name": "harsh_cornering_events", "dataType": "Int64"},
        {"name": "period_days", "dataType": "Int64"},
        {"name": "connection_name", "dataType": "String"},
        {"name": "exported_at", "dataType": "DateTime"},
        {"name": "source_system", "dataType": "String"},
        {"name": "source_authority", "dataType": "String"},
        {"name": "projection_mode", "dataType": "String"},
    ],
    "LaneStabilityCompany": [
        {"name": "period_start", "dataType": "String"},
        {"name": "period_end", "dataType": "String"},
        {"name": "generated_at", "dataType": "DateTime"},
        {"name": "feed_status", "dataType": "String"},
        {"name": "feed_message", "dataType": "String"},
        {"name": "total_orders", "dataType": "Int64"},
        {"name": "billed_orders", "dataType": "Int64"},
        {"name": "total_revenue", "dataType": "Double"},
        {"name": "total_revenue_source", "dataType": "String"},
        {"name": "total_gm", "dataType": "Double"},
        {"name": "gm_pct", "dataType": "Double"},
        {"name": "total_driver_pay", "dataType": "Double"},
        {"name": "team_subset_revenue", "dataType": "Double"},
        {"name": "team_subset_gm", "dataType": "Double"},
        {"name": "weighted_stable_cov_pct", "dataType": "Double"},
        {"name": "baseline_weighted_stable_cov_pct", "dataType": "Double"},
        {"name": "delta_vs_baseline_pct", "dataType": "Double"},
        {"name": "total_lanes", "dataType": "Int64"},
        {"name": "critical", "dataType": "Int64"},
        {"name": "at_risk", "dataType": "Int64"},
        {"name": "watch", "dataType": "Int64"},
        {"name": "stable", "dataType": "Int64"},
        {"name": "cross_route_lanes", "dataType": "Int64"},
        {"name": "connection_name", "dataType": "String"},
        {"name": "exported_at", "dataType": "DateTime"},
        {"name": "source_system", "dataType": "String"},
        {"name": "source_authority", "dataType": "String"},
        {"name": "projection_mode", "dataType": "String"},
    ],
    "LaneStabilityByService": [
        {"name": "period_start", "dataType": "String"},
        {"name": "period_end", "dataType": "String"},
        {"name": "feed_status", "dataType": "String"},
        {"name": "service", "dataType": "String"},
        {"name": "lanes", "dataType": "Int64"},
        {"name": "critical", "dataType": "Int64"},
        {"name": "at_risk", "dataType": "Int64"},
        {"name": "watch", "dataType": "Int64"},
        {"name": "stable", "dataType": "Int64"},
        {"name": "cross_route", "dataType": "Int64"},
        {"name": "orders", "dataType": "Int64"},
        {"name": "revenue", "dataType": "Double"},
        {"name": "gm", "dataType": "Double"},
        {"name": "gm_pct", "dataType": "Double"},
        {"name": "weighted_stable_cov_pct", "dataType": "Double"},
        {"name": "connection_name", "dataType": "String"},
        {"name": "exported_at", "dataType": "DateTime"},
        {"name": "source_system", "dataType": "String"},
        {"name": "source_authority", "dataType": "String"},
        {"name": "projection_mode", "dataType": "String"},
    ],
    "LaneStabilityLanes": [
        {"name": "period_start", "dataType": "String"},
        {"name": "period_end", "dataType": "String"},
        {"name": "feed_status", "dataType": "String"},
        {"name": "service", "dataType": "String"},
        {"name": "lane", "dataType": "String"},
        {"name": "status", "dataType": "String"},
        {"name": "status_rank", "dataType": "Int64"},
        {"name": "orders", "dataType": "Int64"},
        {"name": "unique_drivers", "dataType": "Int64"},
        {"name": "stable_driver", "dataType": "String"},
        {"name": "stable_runs", "dataType": "Int64"},
        {"name": "stable_cov_pct", "dataType": "Double"},
        {"name": "swaps", "dataType": "Int64"},
        {"name": "swap_rate_pct", "dataType": "Double"},
        {"name": "revenue", "dataType": "Double"},
        {"name": "gm", "dataType": "Double"},
        {"name": "gm_pct", "dataType": "Double"},
        {"name": "driver_pay", "dataType": "Double"},
        {"name": "num_routes", "dataType": "Int64"},
        {"name": "primary_route", "dataType": "String"},
        {"name": "primary_route_pct", "dataType": "Double"},
        {"name": "cross_route", "dataType": "bool"},
        {"name": "routes_used", "dataType": "String"},
        {"name": "connection_name", "dataType": "String"},
        {"name": "exported_at", "dataType": "DateTime"},
        {"name": "source_system", "dataType": "String"},
        {"name": "source_authority", "dataType": "String"},
        {"name": "projection_mode", "dataType": "String"},
    ],
    "LaneStabilityRoutes": [
        {"name": "period_start", "dataType": "String"},
        {"name": "period_end", "dataType": "String"},
        {"name": "feed_status", "dataType": "String"},
        {"name": "service", "dataType": "String"},
        {"name": "lane", "dataType": "String"},
        {"name": "route", "dataType": "String"},
        {"name": "orders", "dataType": "Int64"},
        {"name": "route_pct_of_lane", "dataType": "Double"},
        {"name": "primary_driver", "dataType": "String"},
        {"name": "primary_driver_runs", "dataType": "Int64"},
        {"name": "route_stable_cov_pct", "dataType": "Double"},
        {"name": "lane_stable_cov_pct", "dataType": "Double"},
        {"name": "lane_status", "dataType": "String"},
        {"name": "lane_status_rank", "dataType": "Int64"},
        {"name": "revenue", "dataType": "Double"},
        {"name": "gm", "dataType": "Double"},
        {"name": "gm_pct", "dataType": "Double"},
        {"name": "connection_name", "dataType": "String"},
        {"name": "exported_at", "dataType": "DateTime"},
        {"name": "source_system", "dataType": "String"},
        {"name": "source_authority", "dataType": "String"},
        {"name": "projection_mode", "dataType": "String"},
    ],
    "LaneStabilityDaily": [
        {"name": "period_start", "dataType": "String"},
        {"name": "period_end", "dataType": "String"},
        {"name": "feed_status", "dataType": "String"},
        {"name": "date", "dataType": "String"},
        {"name": "orders", "dataType": "Int64"},
        {"name": "active_lanes", "dataType": "Int64"},
        {"name": "active_drivers", "dataType": "Int64"},
        {"name": "revenue", "dataType": "Double"},
        {"name": "gm", "dataType": "Double"},
        {"name": "driver_pay", "dataType": "Double"},
        {"name": "daily_stable_cov_pct", "dataType": "Double"},
        {"name": "connection_name", "dataType": "String"},
        {"name": "exported_at", "dataType": "DateTime"},
        {"name": "source_system", "dataType": "String"},
        {"name": "source_authority", "dataType": "String"},
        {"name": "projection_mode", "dataType": "String"},
    ],
    "LaneStabilityTrend": [
        {"name": "period_start", "dataType": "String"},
        {"name": "period_end", "dataType": "String"},
        {"name": "service", "dataType": "String"},
        {"name": "lane", "dataType": "String"},
        {"name": "trend_type", "dataType": "String"},
        {"name": "baseline_stable_cov_pct", "dataType": "Double"},
        {"name": "current_stable_cov_pct", "dataType": "Double"},
        {"name": "delta_stable_cov_pct", "dataType": "Double"},
        {"name": "baseline_status", "dataType": "String"},
        {"name": "current_status", "dataType": "String"},
        {"name": "current_revenue", "dataType": "Double"},
        {"name": "current_orders", "dataType": "Int64"},
        {"name": "current_num_routes", "dataType": "Int64"},
        {"name": "current_primary_route", "dataType": "String"},
        {"name": "connection_name", "dataType": "String"},
        {"name": "exported_at", "dataType": "DateTime"},
        {"name": "source_system", "dataType": "String"},
        {"name": "source_authority", "dataType": "String"},
        {"name": "projection_mode", "dataType": "String"},
    ],
}


def get_token() -> str:
    env_token = os.getenv("POWERBI_ACCESS_TOKEN")
    if env_token:
        return env_token
    completed = subprocess.run(
        [
            "az",
            "account",
            "get-access-token",
            "--resource",
            "https://analysis.windows.net/powerbi/api",
            "--query",
            "accessToken",
            "-o",
            "tsv",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def get_fabric_token() -> str:
    env_token = os.getenv("FABRIC_ACCESS_TOKEN")
    if env_token:
        return env_token
    completed = subprocess.run(
        [
            "az",
            "account",
            "get-access-token",
            "--resource",
            "https://api.fabric.microsoft.com",
            "--query",
            "accessToken",
            "-o",
            "tsv",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def request_json(
    token: str,
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    *,
    accept_empty: bool = False,
) -> Any:
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status == 202 and response.headers.get("Location"):
                return poll_operation(token, response.headers["Location"])
            raw = response.read()
            if not raw:
                return None if accept_empty else {}
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed HTTP {exc.code}: {detail[:1000]}") from exc


def poll_operation(token: str, operation_url: str) -> Any:
    for _ in range(30):
        request = urllib.request.Request(operation_url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(request, timeout=60) as response:
            status_payload = json.loads(response.read().decode("utf-8"))
        status = status_payload.get("status")
        if status == "Succeeded":
            result_request = urllib.request.Request(
                operation_url.rstrip("/") + "/result",
                headers={"Authorization": f"Bearer {token}"},
            )
            try:
                with urllib.request.urlopen(result_request, timeout=60) as result_response:
                    raw = result_response.read()
                    return json.loads(raw.decode("utf-8")) if raw else status_payload
            except urllib.error.HTTPError:
                return status_payload
        if status == "Failed":
            raise RuntimeError(f"Async operation failed: {json.dumps(status_payload)[:1000]}")
        time.sleep(2)
    raise RuntimeError(f"Async operation did not complete: {operation_url}")


def fetch_fleetpulse(path: str) -> list[dict[str, Any]]:
    request = urllib.request.Request(FLEETPULSE_BASE_URL + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"{path} did not return a row list")
    return payload


def normalize_rows_for_schema(table_name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    columns = [column["name"] for column in TABLE_SCHEMAS[table_name]]
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append({column: row.get(column) for column in columns})
    return normalized


def powerbi_url(path: str) -> str:
    return f"{POWERBI_API}/groups/{WORKSPACE_ID}{path}"


def fabric_url(path: str) -> str:
    return f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}{path}"


def list_items(token: str, kind: str) -> list[dict[str, Any]]:
    payload = request_json(token, "GET", powerbi_url(f"/{kind}"))
    return payload.get("value", [])


def find_by_name(items: list[dict[str, Any]], name_key: str, name: str) -> dict[str, Any] | None:
    for item in items:
        if item.get(name_key) == name:
            return item
    return None


def create_dataset(token: str) -> dict[str, Any]:
    tables = [
        {
            "name": table_name,
            "columns": columns,
        }
        for table_name, columns in TABLE_SCHEMAS.items()
    ]
    return request_json(
        token,
        "POST",
        powerbi_url("/datasets"),
        {
            "name": DATASET_NAME,
            "defaultMode": "Push",
            "tables": tables,
        },
    )


def put_table_schema(token: str, dataset_id: str, table_name: str) -> None:
    request_json(
        token,
        "PUT",
        powerbi_url(f"/datasets/{dataset_id}/tables/{table_name}"),
        {
            "name": table_name,
            "columns": TABLE_SCHEMAS[table_name],
        },
        accept_empty=True,
    )


def clear_table(token: str, dataset_id: str, table_name: str) -> None:
    request_json(
        token,
        "DELETE",
        powerbi_url(f"/datasets/{dataset_id}/tables/{table_name}/rows"),
        accept_empty=True,
    )


def push_rows(token: str, dataset_id: str, table_name: str, rows: list[dict[str, Any]]) -> None:
    for index in range(0, len(rows), 5000):
        chunk = rows[index : index + 5000]
        request_json(
            token,
            "POST",
            powerbi_url(f"/datasets/{dataset_id}/tables/{table_name}/rows"),
            {"rows": chunk},
            accept_empty=True,
        )


def create_dashboard(token: str) -> dict[str, Any]:
    return request_json(token, "POST", powerbi_url("/dashboards"), {"name": DASHBOARD_NAME})


def clone_report(token: str, dataset_id: str) -> dict[str, Any] | None:
    if not ENABLE_CLONE:
        return {"skipped": True, "reason": "POWERBI_ENABLE_CLONE=false"}
    reports = list_items(token, "reports")
    existing = find_by_name(reports, "name", CLONE_REPORT_NAME)
    if existing:
        return existing
    try:
        return request_json(
            token,
            "POST",
            powerbi_url(f"/reports/{SOURCE_REPORT_ID}/Clone"),
            {
                "name": CLONE_REPORT_NAME,
                "targetWorkspaceId": WORKSPACE_ID,
                "targetModelId": dataset_id,
            },
        )
    except RuntimeError as exc:
        return {
            "clone_error": str(exc),
            "name": CLONE_REPORT_NAME,
        }


def encoded_part(path: str, payload: dict[str, Any]) -> dict[str, str]:
    raw = json.dumps(payload, indent=2).encode("utf-8")
    return {
        "path": path,
        "payload": b64encode(raw).decode("ascii"),
        "payloadType": "InlineBase64",
    }


def source_ref(table_name: str) -> dict[str, Any]:
    return {"SourceRef": {"Entity": table_name}}


def column_field(table_name: str, column_name: str) -> dict[str, Any]:
    return {
        "Column": {
            "Expression": source_ref(table_name),
            "Property": column_name,
        }
    }


def sum_field(table_name: str, column_name: str) -> dict[str, Any]:
    return {
        "Aggregation": {
            "Expression": column_field(table_name, column_name),
            "Function": 0,
        }
    }


def column_projection(table_name: str, column_name: str, *, active: bool = False) -> dict[str, Any]:
    projection: dict[str, Any] = {
        "field": column_field(table_name, column_name),
        "queryRef": f"{table_name}.{column_name}",
        "nativeQueryRef": column_name,
    }
    if active:
        projection["active"] = True
    return projection


def sum_projection(table_name: str, column_name: str) -> dict[str, Any]:
    return {
        "field": sum_field(table_name, column_name),
        "queryRef": f"Sum({table_name}.{column_name})",
        "nativeQueryRef": f"Sum of {column_name}",
    }


def pivot_visual(
    name: str,
    x: float,
    y: float,
    width: float,
    height: float,
    rows: list[dict[str, Any]],
    values: list[dict[str, Any]],
) -> dict[str, Any]:
    query_state: dict[str, Any] = {"Values": {"projections": values}}
    if rows:
        query_state["Rows"] = {"projections": rows}
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.8.0/schema.json",
        "name": name,
        "position": {
            "x": x,
            "y": y,
            "z": 0,
            "height": height,
            "width": width,
            "tabOrder": 0,
        },
        "visual": {
            "visualType": "pivotTable",
            "query": {"queryState": query_state},
            "drillFilterOtherVisuals": True,
        },
        "filterConfig": {"filters": []},
    }


def text_visual(name: str, x: float, y: float, width: float, height: float, text: str) -> dict[str, Any]:
    # Power BI accepts HTML-like rich text for textbox visuals in PBIR.
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.8.0/schema.json",
        "name": name,
        "position": {
            "x": x,
            "y": y,
            "z": 10,
            "height": height,
            "width": width,
            "tabOrder": 0,
        },
        "visual": {
            "visualType": "textbox",
            "objects": {
                "general": [
                    {
                        "properties": {
                            "paragraphs": [
                                {
                                    "textRuns": [
                                        {
                                            "value": text,
                                            "textStyle": {"fontSize": "18pt"},
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                ]
            },
        },
    }


def build_native_report_definition(dataset_id: str) -> dict[str, Any]:
    page_name = "fleetpulseops"
    lane_page_name = "lanestability"
    theme_name = "K1FleetPulse"
    visuals = {
        "title": text_visual(
            "title",
            24,
            18,
            1200,
            60,
            "FleetPulse Live Operations - read-only Geotab projection",
        ),
        "overview": pivot_visual(
            "overview",
            24,
            100,
            1220,
            160,
            [],
            [
                sum_projection("FleetPulseOverview", "total_vehicles"),
                sum_projection("FleetPulseOverview", "active"),
                sum_projection("FleetPulseOverview", "parked"),
                sum_projection("FleetPulseOverview", "offline"),
                sum_projection("FleetPulseOverview", "total_trips_today"),
                sum_projection("FleetPulseOverview", "total_stops_today"),
                sum_projection("FleetPulseOverview", "total_distance_miles"),
                sum_projection("FleetPulseOverview", "trips_meeting_target"),
            ],
        ),
        "locations": pivot_visual(
            "locations",
            24,
            290,
            580,
            380,
            [column_projection("FleetPulseLocations", "name", active=True)],
            [
                sum_projection("FleetPulseLocations", "vehicle_count"),
                sum_projection("FleetPulseLocations", "active"),
                sum_projection("FleetPulseLocations", "safety_score"),
            ],
        ),
        "safety": pivot_visual(
            "safety",
            634,
            290,
            610,
            380,
            [column_projection("FleetPulseSafetyScores", "vehicle_name", active=True)],
            [
                sum_projection("FleetPulseSafetyScores", "score"),
                sum_projection("FleetPulseSafetyScores", "event_count"),
                sum_projection("FleetPulseSafetyScores", "speeding_events"),
                sum_projection("FleetPulseSafetyScores", "harsh_braking_events"),
            ],
        ),
    }
    lane_visuals = {
        "lane_title": text_visual(
            "lane_title",
            24,
            18,
            1200,
            60,
            "Lane Stability - read-only Xcelerator operational projection",
        ),
        "lane_company": pivot_visual(
            "lane_company",
            24,
            100,
            1220,
            150,
            [],
            [
                sum_projection("LaneStabilityCompany", "total_revenue"),
                sum_projection("LaneStabilityCompany", "weighted_stable_cov_pct"),
                sum_projection("LaneStabilityCompany", "critical"),
                sum_projection("LaneStabilityCompany", "at_risk"),
                sum_projection("LaneStabilityCompany", "cross_route_lanes"),
            ],
        ),
        "lane_service": pivot_visual(
            "lane_service",
            24,
            280,
            580,
            380,
            [column_projection("LaneStabilityByService", "service", active=True)],
            [
                sum_projection("LaneStabilityByService", "lanes"),
                sum_projection("LaneStabilityByService", "orders"),
                sum_projection("LaneStabilityByService", "revenue"),
                sum_projection("LaneStabilityByService", "weighted_stable_cov_pct"),
                sum_projection("LaneStabilityByService", "cross_route"),
            ],
        ),
        "lane_problem": pivot_visual(
            "lane_problem",
            634,
            280,
            610,
            180,
            [
                column_projection("LaneStabilityLanes", "service", active=True),
                column_projection("LaneStabilityLanes", "lane"),
                column_projection("LaneStabilityLanes", "status"),
                column_projection("LaneStabilityLanes", "primary_route"),
            ],
            [
                sum_projection("LaneStabilityLanes", "orders"),
                sum_projection("LaneStabilityLanes", "revenue"),
                sum_projection("LaneStabilityLanes", "stable_cov_pct"),
                sum_projection("LaneStabilityLanes", "num_routes"),
            ],
        ),
        "lane_trend": pivot_visual(
            "lane_trend",
            634,
            490,
            610,
            170,
            [
                column_projection("LaneStabilityTrend", "trend_type", active=True),
                column_projection("LaneStabilityTrend", "service"),
                column_projection("LaneStabilityTrend", "lane"),
            ],
            [
                sum_projection("LaneStabilityTrend", "current_revenue"),
                sum_projection("LaneStabilityTrend", "current_orders"),
                sum_projection("LaneStabilityTrend", "delta_stable_cov_pct"),
            ],
        ),
    }

    parts = [
        encoded_part(
            "definition.pbir",
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
                "version": "4.0",
                "datasetReference": {
                    "byConnection": {
                        "connectionString": f"semanticmodelid={dataset_id}",
                    }
                },
            },
        ),
        encoded_part(
            "definition/version.json",
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
                "version": "2.0.0",
            },
        ),
        encoded_part(
            "definition/report.json",
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.2.0/schema.json",
                "themeCollection": {
                    "baseTheme": {
                        "name": theme_name,
                        "reportVersionAtImport": {
                            "visual": "2.8.0",
                            "report": "3.2.0",
                            "page": "2.3.1",
                        },
                        "type": "SharedResources",
                    }
                },
                "resourcePackages": [
                    {
                        "name": "SharedResources",
                        "type": "SharedResources",
                        "items": [
                            {
                                "name": theme_name,
                                "path": f"BaseThemes/{theme_name}.json",
                                "type": "BaseTheme",
                            }
                        ],
                    }
                ],
                "settings": {
                    "useStylableVisualContainerHeader": True,
                    "exportDataMode": "AllowSummarized",
                    "defaultDrillFilterOtherVisuals": True,
                    "allowChangeFilterTypes": True,
                    "useEnhancedTooltips": True,
                },
            },
        ),
        encoded_part(
            f"StaticResources/SharedResources/BaseThemes/{theme_name}.json",
            {
                "name": theme_name,
                "dataColors": [
                    "#1f6feb",
                    "#16803c",
                    "#b7791f",
                    "#b42318",
                    "#6f42c1",
                    "#0f766e",
                    "#374151",
                    "#0891b2",
                ],
                "foreground": "#172033",
                "foregroundNeutralSecondary": "#637083",
                "foregroundNeutralTertiary": "#8a94a6",
                "background": "#ffffff",
                "backgroundLight": "#f4f6f8",
                "tableAccent": "#1f6feb",
                "good": "#16803c",
                "neutral": "#b7791f",
                "bad": "#b42318",
            },
        ),
        encoded_part(
            "definition/pages/pages.json",
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
                "pageOrder": [page_name, lane_page_name],
                "activePageName": page_name,
            },
        ),
        encoded_part(
            f"definition/pages/{page_name}/page.json",
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
                "name": page_name,
                "displayName": "FleetPulse Live Operations",
                "displayOption": "FitToPage",
                "height": 720,
                "width": 1280,
            },
        ),
        encoded_part(
            f"definition/pages/{lane_page_name}/page.json",
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
                "name": lane_page_name,
                "displayName": "Lane Stability",
                "displayOption": "FitToPage",
                "height": 720,
                "width": 1280,
            },
        ),
    ]
    for visual_name, visual_payload in visuals.items():
        parts.append(encoded_part(f"definition/pages/{page_name}/visuals/{visual_name}/visual.json", visual_payload))
    for visual_name, visual_payload in lane_visuals.items():
        parts.append(
            encoded_part(f"definition/pages/{lane_page_name}/visuals/{visual_name}/visual.json", visual_payload)
        )
    return {"format": "PBIR", "parts": parts}


def create_native_report(fabric_token: str, powerbi_token: str, dataset_id: str) -> dict[str, Any]:
    reports = list_items(powerbi_token, "reports")
    existing = find_by_name(reports, "name", NATIVE_REPORT_NAME)
    if existing:
        return existing
    return request_json(
        fabric_token,
        "POST",
        fabric_url("/reports"),
        {
            "displayName": NATIVE_REPORT_NAME,
            "definition": build_native_report_definition(dataset_id),
        },
    )


def main() -> int:
    token = get_token()
    fabric_token = get_fabric_token()
    rows_by_table = {
        table_name: normalize_rows_for_schema(table_name, fetch_fleetpulse(endpoint))
        for table_name, endpoint in TABLE_ENDPOINTS.items()
    }

    datasets = list_items(token, "datasets")
    dataset = find_by_name(datasets, "name", DATASET_NAME)
    created_dataset = False
    if dataset is None:
        dataset = create_dataset(token)
        created_dataset = True
    dataset_id = dataset["id"]

    for table_name in TABLE_SCHEMAS:
        if not created_dataset:
            put_table_schema(token, dataset_id, table_name)
            clear_table(token, dataset_id, table_name)
        push_rows(token, dataset_id, table_name, rows_by_table[table_name])

    dashboards = list_items(token, "dashboards")
    dashboard = find_by_name(dashboards, "displayName", DASHBOARD_NAME)
    created_dashboard = False
    if dashboard is None:
        dashboard = create_dashboard(token)
        created_dashboard = True

    report = clone_report(token, dataset_id)
    native_report = create_native_report(fabric_token, token, dataset_id)

    result = {
        "workspace": {"id": WORKSPACE_ID, "name": WORKSPACE_NAME},
        "dataset": {
            "id": dataset_id,
            "name": DATASET_NAME,
            "created": created_dataset,
            "webUrl": dataset.get("webUrl"),
        },
        "dashboard": {
            "id": dashboard.get("id"),
            "name": dashboard.get("displayName") or dashboard.get("name"),
            "created": created_dashboard,
            "webUrl": dashboard.get("webUrl"),
        },
        "report": report,
        "native_report": native_report,
        "row_counts": {name: len(rows) for name, rows in rows_by_table.items()},
        "source": {
            "base_url": FLEETPULSE_BASE_URL,
            "authority": "Geotab",
            "projection_mode": "read_only",
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
