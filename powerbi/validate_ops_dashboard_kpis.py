#!/usr/bin/env python3
"""Validate role-based FleetPulse ops dashboard KPI readiness."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any
import urllib.error
import urllib.request


CONTRACT_PATH = Path(__file__).with_name("ops_kpi_contract.json")
MISSING = object()


def load_contract(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def fetch_json(url: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.getcode())
            content_type = response.headers.get("Content-Type", "")
            text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": int(exc.code),
            "content_type": exc.headers.get("Content-Type", ""),
            "error": "http_error",
            "body_prefix": text[:240],
        }
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "status": None,
            "content_type": "",
            "error": "url_error",
            "detail": str(exc.reason),
        }

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        stripped = text.lstrip().lower()
        error = "html_response" if stripped.startswith("<!doctype html") or stripped.startswith("<html") else "non_json_response"
        return {
            "ok": False,
            "status": status,
            "content_type": content_type,
            "error": error,
            "body_prefix": text[:240],
        }

    return {
        "ok": True,
        "status": status,
        "content_type": content_type,
        "payload": payload,
    }


def get_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, list):
            try:
                index = int(part)
            except ValueError:
                current = current[0] if current else MISSING
                if current is MISSING:
                    return MISSING
            else:
                if index >= len(current):
                    return MISSING
                current = current[index]
                continue
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return MISSING
    return current


def representative_row(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    return None


def walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for item in value:
            yield from walk_dicts(item)


def find_named_status(payload: Any, name_contains: str) -> dict[str, Any] | None:
    needle = name_contains.casefold()
    for item in walk_dicts(payload):
        name = str(item.get("name", ""))
        if needle in name.casefold() and "status" in item:
            return item
    return None


def parse_iso_datetime(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def validate_payload(check: dict[str, Any], payload: Any) -> tuple[bool, list[dict[str, Any]], dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}
    expected_type = check.get("payload_type")

    if expected_type == "object" and not isinstance(payload, dict):
        errors.append({"error": "payload_not_object"})
        return False, errors, metadata
    if expected_type == "list" and not isinstance(payload, list):
        errors.append({"error": "payload_not_list"})
        return False, errors, metadata
    if isinstance(payload, list):
        metadata["row_count"] = len(payload)
        if check.get("require_non_empty", False) and not payload:
            errors.append({"error": "empty_payload"})
        if not payload and not check.get("require_non_empty", False):
            return not errors, errors, metadata

    row = representative_row(payload)
    expected_authority = check.get("expected_source_authority")
    if expected_authority:
        actual_authority = row.get("source_authority") if row else None
        metadata["source_authority"] = actual_authority
        if actual_authority != expected_authority:
            errors.append(
                {
                    "error": "source_authority_mismatch",
                    "expected": expected_authority,
                    "actual": actual_authority,
                }
            )

    expected_projection_mode = check.get("expected_projection_mode")
    if expected_projection_mode:
        actual_projection_mode = row.get("projection_mode") if row else None
        metadata["projection_mode"] = actual_projection_mode
        if actual_projection_mode != expected_projection_mode:
            errors.append(
                {
                    "error": "projection_mode_mismatch",
                    "expected": expected_projection_mode,
                    "actual": actual_projection_mode,
                }
            )

    validation_root = row if isinstance(payload, list) else payload
    for field in check.get("required_fields", []):
        if get_path(validation_root, field) is MISSING:
            errors.append({"error": "missing_required_field", "field": field})

    for minimum in check.get("minimums", []):
        value = get_path(payload, minimum["path"])
        if value is MISSING:
            errors.append({"error": "missing_minimum_field", "field": minimum["path"]})
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            errors.append({"error": "minimum_field_not_numeric", "field": minimum["path"], "actual": value})
            continue
        if numeric < float(minimum["min"]):
            errors.append(
                {
                    "error": "minimum_not_met",
                    "field": minimum["path"],
                    "minimum": minimum["min"],
                    "actual": value,
                }
            )

    for expected in check.get("expected_values", []):
        value = get_path(payload, expected["path"])
        if value is MISSING:
            errors.append({"error": "missing_expected_value_field", "field": expected["path"]})
            continue
        if value != expected["value"]:
            errors.append(
                {
                    "error": "expected_value_mismatch",
                    "field": expected["path"],
                    "expected": expected["value"],
                    "actual": value,
                }
            )

    now = datetime.now(timezone.utc)
    for timestamp in check.get("recent_timestamps", []):
        value = get_path(payload, timestamp["path"])
        parsed = parse_iso_datetime(value)
        if parsed is None:
            errors.append({"error": "timestamp_invalid", "field": timestamp["path"], "actual": value})
            continue
        max_age_hours = float(timestamp["max_age_hours"])
        age_hours = (now - parsed).total_seconds() / 3600
        metadata[f"{timestamp['path']}_age_hours"] = round(age_hours, 2)
        if age_hours > max_age_hours:
            errors.append(
                {
                    "error": "timestamp_stale",
                    "field": timestamp["path"],
                    "max_age_hours": max_age_hours,
                    "actual_age_hours": round(age_hours, 2),
                    "actual": value,
                }
            )

    for status_check in check.get("named_statuses", []):
        item = find_named_status(payload, status_check["name_contains"])
        if not item:
            errors.append({"error": "named_status_missing", "name_contains": status_check["name_contains"]})
            continue
        actual_status = str(item.get("status", "")).lower()
        allowed = [str(status).lower() for status in status_check["allowed_statuses"]]
        metadata[f"{status_check['name_contains']}_status"] = actual_status
        if actual_status not in allowed:
            errors.append(
                {
                    "error": "named_status_not_allowed",
                    "name": item.get("name"),
                    "expected_any_of": allowed,
                    "actual": actual_status,
                    "detail": item.get("detail") or item.get("message"),
                }
            )

    return not errors, errors, metadata


def validate_check(
    check: dict[str, Any],
    base_url: str,
    timeout: int,
    cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    url = join_url(base_url, check["path"])
    fetched = cache.setdefault(check["path"], fetch_json(url, timeout))
    result: dict[str, Any] = {
        "id": check["id"],
        "path": check["path"],
        "url": url,
        "required": bool(check.get("required", True)),
        "ok": False,
        "status": fetched.get("status"),
        "content_type": fetched.get("content_type"),
    }
    if not fetched.get("ok"):
        result["error"] = fetched.get("error")
        if "detail" in fetched:
            result["detail"] = fetched["detail"]
        if "body_prefix" in fetched:
            result["body_prefix"] = fetched["body_prefix"]
        return result

    ok, errors, metadata = validate_payload(check, fetched["payload"])
    result["ok"] = ok
    if errors:
        result["errors"] = errors
    result.update(metadata)
    return result


def validate_role(
    role: dict[str, Any],
    base_url: str,
    timeout: int,
    cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    checks = [validate_check(check, base_url, timeout, cache) for check in role.get("endpoint_checks", [])]
    required_failures = [check for check in checks if check.get("required", True) and not check.get("ok")]
    optional_failures = [check for check in checks if not check.get("required", True) and not check.get("ok")]
    status = "blocked" if required_failures else ("needs_attention" if optional_failures or role.get("known_limitations") else "verified")
    return {
        "id": role["id"],
        "label": role["label"],
        "certification_status": status,
        "source_boundary": role.get("source_boundary"),
        "kpis": role.get("kpis", []),
        "known_limitations": role.get("known_limitations", []),
        "checks_passed": sum(1 for check in checks if check.get("ok")),
        "checks_total": len(checks),
        "checks": checks,
    }


def summarize_text(report: dict[str, Any]) -> str:
    lines = [
        f"FleetPulse Ops KPI Verification - {report['base_url']}",
        f"Overall: {report['overall_status']}",
        "",
    ]
    for role in report["roles"]:
        lines.append(
            f"{role['label']}: {role['certification_status']} "
            f"({role['checks_passed']}/{role['checks_total']} checks passed)"
        )
        for check in role["checks"]:
            marker = "OK" if check.get("ok") else "FAIL"
            detail = check.get("error")
            if not detail and check.get("errors"):
                detail = check["errors"][0].get("error")
            suffix = f" - {detail}" if detail else ""
            lines.append(f"  {marker} {check['id']}{suffix}")
        if role.get("known_limitations") and role["certification_status"] != "blocked":
            lines.append("  NOTE known limitations remain; see JSON report for details.")
        lines.append("")
    return "\n".join(lines).rstrip()


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    contract = load_contract(args.contract)
    base_url = args.base_url or os.getenv(contract.get("base_url_env", ""), "") or contract["default_base_url"]
    selected_roles = set(args.role or [])
    roles = [
        role
        for role in contract["roles"]
        if not selected_roles or role["id"] in selected_roles
    ]
    if selected_roles and len(roles) != len(selected_roles):
        found = {role["id"] for role in roles}
        missing = sorted(selected_roles - found)
        raise SystemExit(f"Unknown role id(s): {', '.join(missing)}")

    cache: dict[str, dict[str, Any]] = {}
    role_reports = [validate_role(role, base_url, args.timeout, cache) for role in roles]
    if any(role["certification_status"] == "blocked" for role in role_reports):
        overall_status = "blocked"
    elif any(role["certification_status"] == "needs_attention" for role in role_reports):
        overall_status = "needs_attention"
    else:
        overall_status = "verified"

    return {
        "contract_name": contract["contract_name"],
        "contract_version": contract["version"],
        "base_url": base_url,
        "overall_status": overall_status,
        "roles": role_reports,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH, help="Path to ops KPI contract JSON.")
    parser.add_argument("--base-url", help="FleetPulse base URL. Defaults to contract env or deployed production URL.")
    parser.add_argument("--role", action="append", help="Role id to validate. May be passed more than once.")
    parser.add_argument("--timeout", type=int, default=45, help="HTTP timeout in seconds.")
    parser.add_argument(
        "--allow-needs-attention",
        action="store_true",
        help="Exit successfully when checks pass but known limitations keep the result at needs_attention.",
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(summarize_text(report))
    if report["overall_status"] == "verified":
        return 0
    if args.allow_needs_attention and report["overall_status"] == "needs_attention":
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
