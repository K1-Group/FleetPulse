from datetime import datetime
from types import SimpleNamespace

from services import revenue_productivity_service as service


class _FakeGeotabClient:
    def __init__(self, trips):
        self._trips = trips

    def get_trips(self, from_date=None, to_date=None):
        return self._trips


def _trip(device_id: str, miles: float, driver_id: str | None = None):
    row = {
        "device": {"id": device_id},
        "distance": miles / 0.621371,
    }
    if driver_id:
        row["driver"] = {"id": driver_id, "name": driver_id}
    return row


def _geotab_warehouse_rows(query):
    if "objects.name = 'ntta_geotab_daily_report'" in query:
        return [
            {"column_name": "Date"},
            {"column_name": "DeviceId"},
            {"column_name": "Distance_Miles"},
        ]
    if "ntta_geotab_daily_report" in query and "FROM sys.objects" in query:
        return [{"table_schema": "dbo", "table_name": "ntta_geotab_daily_report"}]
    if "[dbo].[ntta_geotab_daily_report]" in query:
        return [
            {"vehicle_key": "truck-1", "miles": 120, "source_rows": 3},
            {"vehicle_key": "truck-2", "miles": 80, "source_rows": 2},
        ]
    return None


def test_revenue_productivity_uses_xcelerator_revenue_and_drivers(monkeypatch):
    monkeypatch.setattr(
        service.GeotabClient,
        "get",
        lambda: _FakeGeotabClient(
            [
                _trip("truck-1", 120, "geo-driver-1"),
                _trip("truck-2", 80, "geo-driver-2"),
            ]
        ),
    )
    monkeypatch.setattr(service.FabricWarehouseSqlConfig, "from_env", lambda prefix: SimpleNamespace(configured=True))

    def fake_sql(config, query):
        geotab_rows = _geotab_warehouse_rows(query)
        if geotab_rows is not None:
            return geotab_rows
        if "GROUP BY schemas.name" in query:
            return [{"table_schema": "dbo", "table_name": "xcelerator_review_orders"}]
        if "columns.name AS column_name" in query:
            return [
                {"column_name": "pickup_target_from"},
                {"column_name": "delivery_center"},
                {"column_name": "grand_total_amount"},
                {"column_name": "driver_no"},
            ]
        return [
            {
                "pickup_date": datetime(2026, 5, 11).date(),
                "delivery_center": "K1 Logistics Inc",
                "revenue": 12000,
                "driver_key": "D1",
            },
            {
                "pickup_date": datetime(2026, 5, 12).date(),
                "delivery_center": "K1 Logistics Inc",
                "revenue": 9000,
                "driver_key": "D2",
            },
            {
                "pickup_date": datetime(2026, 5, 12).date(),
                "delivery_center": "K1 Group LLC",
                "revenue": 7000,
                "driver_key": "D3",
            },
        ]

    monkeypatch.setattr(service, "execute_sql_query", fake_sql)

    snapshot = service.get_revenue_productivity_snapshot(days=7)

    assert snapshot["summary"]["revenue"] == 21000
    assert snapshot["summary"]["truck_count"] == 2
    assert snapshot["summary"]["driver_count"] == 2
    assert snapshot["summary"]["driver_source"] == "xcelerator_review_orders"
    assert snapshot["summary"]["revenue_per_truck"] == 10500
    assert snapshot["summary"]["revenue_per_driver"] == 10500
    assert snapshot["summary"]["truck_target_status"] == "above_target"
    assert snapshot["summary"]["driver_target_status"] == "above_target"


def test_revenue_productivity_falls_back_to_geotab_driver_count(monkeypatch):
    monkeypatch.setattr(
        service.GeotabClient,
        "get",
        lambda: _FakeGeotabClient(
            [
                _trip("truck-1", 120, "geo-driver-1"),
                _trip("truck-2", 80, "geo-driver-2"),
            ]
        ),
    )
    monkeypatch.setattr(service.FabricWarehouseSqlConfig, "from_env", lambda prefix: SimpleNamespace(configured=True))

    def fake_sql(config, query):
        geotab_rows = _geotab_warehouse_rows(query)
        if geotab_rows is not None:
            return geotab_rows
        if "GROUP BY schemas.name" in query:
            return [{"table_schema": "dbo", "table_name": "xcelerator_review_orders"}]
        if "columns.name AS column_name" in query:
            return [
                {"column_name": "pickup_target_from"},
                {"column_name": "delivery_center"},
                {"column_name": "grand_total_amount"},
            ]
        return [
            {
                "pickup_date": datetime(2026, 5, 12).date(),
                "delivery_center": "K1 Logistics Inc",
                "revenue": 14000,
                "driver_key": None,
            },
        ]

    monkeypatch.setattr(service, "execute_sql_query", fake_sql)

    snapshot = service.get_revenue_productivity_snapshot(days=7)

    assert snapshot["summary"]["revenue"] == 14000
    assert snapshot["summary"]["truck_count"] == 2
    assert snapshot["summary"]["driver_count"] == 2
    assert snapshot["summary"]["driver_source"] == "geotab_trip_driver_fallback"
    assert snapshot["summary"]["revenue_per_truck"] == 7000
    assert snapshot["summary"]["revenue_per_driver"] == 7000


def test_revenue_productivity_uses_warehouse_truck_count_when_geotab_api_is_over_limit(monkeypatch):
    class OverLimitGeotabClient:
        def get_trips(self, from_date=None, to_date=None):
            raise RuntimeError("OverLimitException: API calls quota exceeded")

    monkeypatch.setattr(service.GeotabClient, "get", lambda: OverLimitGeotabClient())
    monkeypatch.setattr(service.FabricWarehouseSqlConfig, "from_env", lambda prefix: SimpleNamespace(configured=True))

    def fake_sql(config, query):
        geotab_rows = _geotab_warehouse_rows(query)
        if geotab_rows is not None:
            return geotab_rows
        if "GROUP BY schemas.name" in query:
            return [{"table_schema": "dbo", "table_name": "xcelerator_review_orders"}]
        if "columns.name AS column_name" in query:
            return [
                {"column_name": "pickup_target_from"},
                {"column_name": "delivery_center"},
                {"column_name": "grand_total_amount"},
                {"column_name": "driver_no"},
            ]
        return [
            {
                "pickup_date": datetime(2026, 5, 12).date(),
                "delivery_center": "K1 Logistics Inc",
                "revenue": 18000,
                "driver_key": "D1",
            },
            {
                "pickup_date": datetime(2026, 5, 12).date(),
                "delivery_center": "K1 Logistics Inc",
                "revenue": 6000,
                "driver_key": "D2",
            },
        ]

    monkeypatch.setattr(service, "execute_sql_query", fake_sql)

    snapshot = service.get_revenue_productivity_snapshot(days=7)

    assert snapshot["summary"]["revenue"] == 24000
    assert snapshot["summary"]["truck_count"] == 2
    assert snapshot["summary"]["driver_count"] == 2
    assert snapshot["summary"]["revenue_per_truck"] == 12000
    assert snapshot["sources"]["trucks"]["path"] == "fabric_warehouse_sql"
    assert snapshot["sources"]["trucks"]["status"] == "healthy"
