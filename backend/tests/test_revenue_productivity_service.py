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
