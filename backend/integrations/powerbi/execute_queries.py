"""Read-only Power BI semantic model query client.

FleetPulse uses this only as an analytics projection. Power BI remains a
read-only surface, and Xcelerator remains authoritative for order, revenue,
and driver-pay facts.
"""

from __future__ import annotations

import io
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from configs.xcelerator_source import xcelerator_refresh_seconds


DEFAULT_XCELERATOR_CEO_WORKSPACE_ID = "b801f80d-5303-4121-abd1-1163639ef58b"
DEFAULT_XCELERATOR_CEO_DATASET_ID = "891e7334-af84-4889-ba7f-ae89864777c0"
POWERBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
_QUERY_CACHE: dict[tuple[str, str, str], tuple[float, list[dict[str, Any]]]] = {}


@dataclass(frozen=True)
class PowerBIExecuteQueriesConfig:
    """Runtime config for Power BI semantic-model query calls."""

    workspace_id: str = ""
    dataset_id: str = ""
    access_token: str = ""
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls, prefix: str = "FLEETPULSE_XCELERATOR_CEO_POWERBI") -> "PowerBIExecuteQueriesConfig":
        timeout_raw = os.getenv(f"{prefix}_TIMEOUT_SECONDS", "10")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError:
            timeout_seconds = 10.0

        return cls(
            workspace_id=(
                os.getenv(f"{prefix}_WORKSPACE_ID", "").strip()
                or DEFAULT_XCELERATOR_CEO_WORKSPACE_ID
            ),
            dataset_id=(
                os.getenv(f"{prefix}_DATASET_ID", "").strip()
                or os.getenv(f"{prefix}_SEMANTIC_MODEL_ID", "").strip()
                or DEFAULT_XCELERATOR_CEO_DATASET_ID
            ),
            access_token=(
                os.getenv(f"{prefix}_ACCESS_TOKEN", "").strip()
                or os.getenv("POWERBI_ACCESS_TOKEN", "").strip()
            ),
            tenant_id=(
                os.getenv(f"{prefix}_TENANT_ID", "").strip()
                or os.getenv("FLEETPULSE_GRAPH_TENANT_ID", "").strip()
            ),
            client_id=(
                os.getenv(f"{prefix}_CLIENT_ID", "").strip()
                or os.getenv("FLEETPULSE_GRAPH_CLIENT_ID", "").strip()
            ),
            client_secret=(
                os.getenv(f"{prefix}_CLIENT_SECRET", "").strip()
                or os.getenv("FLEETPULSE_GRAPH_CLIENT_SECRET", "").strip()
            ),
            timeout_seconds=timeout_seconds,
        )

    @property
    def configured(self) -> bool:
        return bool(
            self.workspace_id
            and self.dataset_id
            and (
                self.access_token
                or (self.tenant_id and self.client_id and self.client_secret)
            )
        )


def _get_access_token(config: PowerBIExecuteQueriesConfig) -> str:
    if config.access_token:
        return config.access_token
    if not (config.tenant_id and config.client_id and config.client_secret):
        raise RuntimeError("powerbi_auth_not_configured")

    token_url = f"https://login.microsoftonline.com/{config.tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "grant_type": "client_credentials",
        "scope": POWERBI_SCOPE,
    }
    with httpx.Client(timeout=config.timeout_seconds) as client:
        response = client.post(token_url, data=data)
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("powerbi_access_token_missing")
    return str(token)


def _parse_arrow_rows(content: bytes) -> list[dict[str, Any]]:
    """Decode Power BI executeDaxQueries Arrow stream rows."""

    try:
        import pyarrow as pa  # type: ignore[import-not-found]
        import pyarrow.ipc as pa_ipc  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("pyarrow_not_installed_for_powerbi_execute_dax_queries") from exc

    stream = io.BytesIO(content)
    rows: list[dict[str, Any]] = []
    while stream.tell() < len(content):
        try:
            with pa_ipc.open_stream(stream) as reader:
                table = reader.read_all()
                metadata = {
                    key.decode(): value.decode()
                    for key, value in (reader.schema.metadata or {}).items()
                }
        except pa.ArrowInvalid:
            break
        if metadata.get("IsError") == "true":
            fault_code = metadata.get("FaultCode") or "unknown"
            fault_string = metadata.get("FaultString") or "Power BI DAX query failed"
            raise RuntimeError(f"powerbi_execute_dax_queries_error[{fault_code}]: {fault_string}")
        rows.extend(row for row in table.to_pylist() if isinstance(row, dict))
    return rows


def _execute_queries_json(
    *,
    config: PowerBIExecuteQueriesConfig,
    token: str,
    query: str,
) -> list[dict[str, Any]]:
    url = (
        "https://api.powerbi.com/v1.0/myorg/groups/"
        f"{config.workspace_id}/datasets/{config.dataset_id}/executeQueries"
    )
    payload = {
        "queries": [{"query": query}],
        "serializerSettings": {"includeNulls": True},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=config.timeout_seconds) as client:
        response = client.post(url, headers=headers, json=payload)
    response.raise_for_status()

    results = response.json().get("results") or []
    if not results:
        return []
    tables = (results[0] or {}).get("tables") or []
    if not tables:
        return []
    rows = (tables[0] or {}).get("rows") or []
    return [row for row in rows if isinstance(row, dict)]


def _execute_dax_queries_arrow(
    *,
    config: PowerBIExecuteQueriesConfig,
    token: str,
    query: str,
) -> list[dict[str, Any]]:
    url = (
        "https://api.powerbi.com/v1.0/myorg/groups/"
        f"{config.workspace_id}/datasets/{config.dataset_id}/executeDaxQueries"
    )
    payload = {
        "query": query,
        "schemaOnly": False,
        "resultSetRowCountLimit": 100000,
    }
    headers = {
        "Accept": "application/vnd.apache.arrow.stream",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=config.timeout_seconds) as client:
        response = client.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return _parse_arrow_rows(response.content)


def execute_dax_query(config: PowerBIExecuteQueriesConfig, query: str) -> list[dict[str, Any]]:
    """Run one DAX query against a Power BI semantic model and return table rows."""

    if not config.configured:
        raise RuntimeError("powerbi_execute_queries_not_configured")

    cache_key = (config.workspace_id, config.dataset_id, query)
    now = time.time()
    cached = _QUERY_CACHE.get(cache_key)
    if cached and cached[0] > now:
        return list(cached[1])

    token = _get_access_token(config)
    try:
        normalized = _execute_queries_json(config=config, token=token, query=query)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in {401, 403}:
            raise
        normalized = _execute_dax_queries_arrow(config=config, token=token, query=query)
    _QUERY_CACHE[cache_key] = (now + xcelerator_refresh_seconds(), normalized)
    return list(normalized)


def clear_execute_queries_cache() -> None:
    """Clear cached Power BI semantic-model results."""

    _QUERY_CACHE.clear()
