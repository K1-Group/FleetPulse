"""Tests for the Fabric Warehouse SQL client."""

from __future__ import annotations

import sys
import types
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from integrations.fabric_warehouse.sql_client import (  # noqa: E402
    FabricWarehouseSqlConfig,
    execute_sql_query,
)


def test_execute_sql_query_applies_statement_timeout(monkeypatch):
    class FakeCursor:
        description = [("answer",)]

        def __init__(self) -> None:
            self.timeout = None
            self.executed_query = None

        def execute(self, query, *params):
            self.executed_query = query
            self.executed_params = params

        def fetchall(self):
            return [(42,)]

    class FakeConnection:
        def __init__(self) -> None:
            self.timeout = None
            self.cursor_instance = FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return self.cursor_instance

    connection = FakeConnection()
    fake_pyodbc = types.SimpleNamespace(
        connect=lambda connection_string, timeout: connection,
    )
    monkeypatch.setitem(sys.modules, "pyodbc", fake_pyodbc)

    config = FabricWarehouseSqlConfig(
        server="warehouse.example.com",
        database="ReportingLakehouse",
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        timeout_seconds=7,
    )

    rows = execute_sql_query(config, "SELECT 42 AS answer")

    assert rows == [{"answer": 42}]
    assert connection.timeout == 7
    assert connection.cursor_instance.timeout == 7
    assert connection.cursor_instance.executed_query == "SELECT 42 AS answer"
    assert connection.cursor_instance.executed_params == ()


def test_execute_sql_query_passes_params(monkeypatch):
    class FakeCursor:
        description = [("answer",)]

        def __init__(self) -> None:
            self.executed_query = None
            self.executed_params = None

        def execute(self, query, *params):
            self.executed_query = query
            self.executed_params = params

        def fetchall(self):
            return [(42,)]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return self.cursor_instance

        def __init__(self) -> None:
            self.cursor_instance = FakeCursor()

    connection = FakeConnection()
    fake_pyodbc = types.SimpleNamespace(connect=lambda connection_string, timeout: connection)
    monkeypatch.setitem(sys.modules, "pyodbc", fake_pyodbc)

    config = FabricWarehouseSqlConfig(
        server="warehouse.example.com",
        database="ReportingLakehouse",
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
    )

    rows = execute_sql_query(config, "SELECT ? AS answer", (42,))

    assert rows == [{"answer": 42}]
    assert connection.cursor_instance.executed_query == "SELECT ? AS answer"
    assert connection.cursor_instance.executed_params == (42,)
