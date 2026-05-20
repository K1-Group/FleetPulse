"""Read-only Fabric Warehouse SQL client.

FleetPulse uses this only for analytics projections. Xcelerator remains the
source of truth for revenue/order facts, and the Warehouse is a read-only
Fabric projection of those facts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Sequence


DEFAULT_XCELERATOR_WAREHOUSE_SERVER = (
    "fe7syha5hsjelmowgsaa2gmtb4-bx4adoadkmqudk6rcfrwhhxvrm"
    ".datawarehouse.fabric.microsoft.com"
)
DEFAULT_XCELERATOR_WAREHOUSE_DATABASE = "K1-BI-WH"
DEFAULT_ODBC_DRIVER = "ODBC Driver 18 for SQL Server"


@dataclass(frozen=True)
class FabricWarehouseSqlConfig:
    """Runtime config for Fabric Warehouse SQL read-only queries."""

    server: str = ""
    database: str = ""
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    driver: str = DEFAULT_ODBC_DRIVER
    timeout_seconds: int = 15

    @classmethod
    def from_env(cls, prefix: str = "FLEETPULSE_XCELERATOR_WAREHOUSE_SQL") -> "FabricWarehouseSqlConfig":
        timeout_raw = os.getenv(f"{prefix}_TIMEOUT_SECONDS", "15")
        try:
            timeout_seconds = max(int(timeout_raw), 1)
        except ValueError:
            timeout_seconds = 15

        return cls(
            server=(
                os.getenv(f"{prefix}_SERVER", "").strip()
                or DEFAULT_XCELERATOR_WAREHOUSE_SERVER
            ),
            database=(
                os.getenv(f"{prefix}_DATABASE", "").strip()
                or DEFAULT_XCELERATOR_WAREHOUSE_DATABASE
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
            driver=os.getenv(f"{prefix}_ODBC_DRIVER", DEFAULT_ODBC_DRIVER).strip() or DEFAULT_ODBC_DRIVER,
            timeout_seconds=timeout_seconds,
        )

    @property
    def configured(self) -> bool:
        return bool(self.server and self.database and self.tenant_id and self.client_id and self.client_secret)

    def connection_string(self) -> str:
        server = self.server
        if "," not in server and ":" not in server:
            server = f"{server},1433"
        return ";".join(
            [
                f"Driver={{{self.driver}}}",
                f"Server={server}",
                f"Database={self.database}",
                "Encrypt=yes",
                "TrustServerCertificate=no",
                "Authentication=ActiveDirectoryServicePrincipal",
                f"UID={self.client_id}",
                f"PWD={self.client_secret}",
                f"Connection Timeout={self.timeout_seconds}",
            ]
        )


def execute_sql_query(
    config: FabricWarehouseSqlConfig,
    query: str,
    params: Sequence[Any] | None = None,
) -> list[dict[str, Any]]:
    """Run a read-only SQL query against Fabric Warehouse and return rows."""

    if not config.configured:
        raise RuntimeError("fabric_warehouse_sql_not_configured")

    try:
        import pyodbc  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("pyodbc_not_installed") from exc

    with pyodbc.connect(config.connection_string(), timeout=config.timeout_seconds) as connection:
        connection.timeout = config.timeout_seconds
        cursor = connection.cursor()
        if hasattr(cursor, "timeout"):
            cursor.timeout = config.timeout_seconds
        if params:
            cursor.execute(query, *params)
        else:
            cursor.execute(query)
        columns = [column[0] for column in (cursor.description or [])]
        return [
            {columns[index]: value for index, value in enumerate(row)}
            for row in cursor.fetchall()
        ]
