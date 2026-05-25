"""Tests for the Power BI semantic-model query client."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from integrations.powerbi import execute_queries  # noqa: E402


def _response(status_code: int, *, json_body: dict | None = None, content: bytes = b"") -> httpx.Response:
    request = httpx.Request("POST", "https://api.powerbi.test/query")
    if json_body is not None:
        return httpx.Response(status_code, json=json_body, request=request)
    return httpx.Response(status_code, content=content, request=request)


class _FakeClient:
    responses: list[httpx.Response] = []
    calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def post(self, url: str, *, headers: dict | None = None, json: dict | None = None, data=None):
        self.calls.append({"url": url, "headers": headers or {}, "json": json, "data": data})
        return self.responses.pop(0)


def _config() -> execute_queries.PowerBIExecuteQueriesConfig:
    return execute_queries.PowerBIExecuteQueriesConfig(
        workspace_id="workspace",
        dataset_id="dataset",
        access_token="token",
    )


def test_execute_dax_query_uses_json_endpoint_when_authorized(monkeypatch):
    execute_queries.clear_execute_queries_cache()
    _FakeClient.calls = []
    _FakeClient.responses = [
        _response(
            200,
            json_body={
                "results": [
                    {
                        "tables": [
                            {
                                "rows": [
                                    {"xcelerator_review_orders[delivery_center]": "K1 Logistics Inc"}
                                ]
                            }
                        ]
                    }
                ]
            },
        )
    ]
    monkeypatch.setattr(execute_queries.httpx, "Client", _FakeClient)

    rows = execute_queries.execute_dax_query(_config(), "EVALUATE TOPN(1, 'xcelerator_review_orders')")

    assert rows == [{"xcelerator_review_orders[delivery_center]": "K1 Logistics Inc"}]
    assert _FakeClient.calls[0]["url"].endswith("/executeQueries")
    assert len(_FakeClient.calls) == 1


def test_execute_dax_query_falls_back_to_arrow_endpoint_for_service_principal(monkeypatch):
    execute_queries.clear_execute_queries_cache()
    _FakeClient.calls = []
    _FakeClient.responses = [
        _response(401, json_body={"error": {"code": "PowerBINotAuthorizedException"}}),
        _response(200, content=b"arrow-stream"),
    ]
    monkeypatch.setattr(execute_queries.httpx, "Client", _FakeClient)
    monkeypatch.setattr(
        execute_queries,
        "_parse_arrow_rows",
        lambda content: [{"[review_orders_count]": 118619}],
    )

    rows = execute_queries.execute_dax_query(_config(), "EVALUATE ROW(\"review_orders_count\", 1)")

    assert rows == [{"[review_orders_count]": 118619}]
    assert _FakeClient.calls[0]["url"].endswith("/executeQueries")
    assert _FakeClient.calls[1]["url"].endswith("/executeDaxQueries")
    assert _FakeClient.calls[1]["json"]["query"] == "EVALUATE ROW(\"review_orders_count\", 1)"
    assert _FakeClient.calls[1]["headers"]["Accept"] == "application/vnd.apache.arrow.stream"
