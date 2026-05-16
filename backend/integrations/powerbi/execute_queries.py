"""Read-only Power BI semantic model query client.

FleetPulse uses this only as an analytics projection. Power BI remains a
read-only surface, and Xcelerator remains authoritative for order, revenue,
and driver-pay facts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


DEFAULT_XCELERATOR_CEO_WORKSPACE_ID = "b801f80d-5303-4121-abd1-1163639ef58b"
DEFAULT_XCELERATOR_CEO_DATASET_ID = "891e7334-af84-4889-ba7f-ae89864777c0"
POWERBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"


@dataclass(frozen=True)
class PowerBIExecuteQueriesConfig:
    """Runtime config for Power BI executeQueries calls."""

    workspace_id: str = ""
    dataset_id: str = ""
    access_token: str = ""
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls, prefix: str = "FLEETPULSE_XCELERATOR_CEO_POWERBI") -> "PowerBIExecuteQueriesConfig":
        timeout_raw = os.getenv(f"{prefix}_TIMEOUT_SECONDS", "30")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError:
            timeout_seconds = 30.0

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


def execute_dax_query(config: PowerBIExecuteQueriesConfig, query: str) -> list[dict[str, Any]]:
    """Run one DAX query against a Power BI semantic model and return table rows."""

    if not config.configured:
        raise RuntimeError("powerbi_execute_queries_not_configured")

    token = _get_access_token(config)
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

