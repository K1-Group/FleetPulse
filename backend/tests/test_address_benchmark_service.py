from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from configs.address_benchmark import AddressBenchmarkConfig
import services.address_benchmark_service as service
from services.address_benchmark_service import build_address_benchmark_dataset


def _now() -> datetime:
    return datetime(2026, 5, 27, tzinfo=timezone.utc)


def test_address_benchmark_compares_drivers_by_pickup_delivery_pair():
    config = AddressBenchmarkConfig(
        period_days=30,
        stop_threshold_minutes=60,
        minimum_history_samples=2,
        cost_per_truck_hour=90.0,
    )
    rows = [
        {
            "OrderTrackingID": "101",
            "DriverNo": "D1",
            "pickup_address": "Fort Worth Yard",
            "delivery_address": "Dallas DC",
            "pickup_departure": "2026-05-20T10:00:00Z",
            "delivery_arrival": "2026-05-20T11:00:00Z",
            "Grand Total": "500",
            "Driver Pay": "180",
        },
        {
            "OrderTrackingID": "102",
            "DriverNo": "D2",
            "pickup_address": "Fort Worth Yard",
            "delivery_address": "Dallas DC",
            "pickup_departure": "2026-05-21T10:00:00Z",
            "delivery_arrival": "2026-05-21T11:30:00Z",
            "Grand Total": "500",
            "Driver Pay": "180",
            "stop_minutes": "75",
        },
        {
            "OrderTrackingID": "103",
            "DriverNo": "D1",
            "pickup_address": "Fort Worth Yard",
            "delivery_address": "Dallas DC",
            "pickup_departure": "2026-05-22T10:00:00Z",
            "delivery_arrival": "2026-05-22T11:20:00Z",
            "Grand Total": "500",
            "Driver Pay": "180",
        },
    ]

    dataset = build_address_benchmark_dataset(rows, config=config, now=_now())

    assert dataset["projection_mode"] == "read_only"
    assert dataset["summary"]["address_pairs"] == 1
    pair = dataset["address_pairs"][0]
    assert pair["pickup_address"] == "Fort Worth Yard"
    assert pair["delivery_address"] == "Dallas DC"
    assert pair["avg_route_minutes"] == 76.7
    assert pair["stop_threshold_minutes"] == 60
    assert pair["stop_events_over_threshold"] == 1
    assert pair["opportunity_minutes_vs_pair_average"] == 16.6
    assert pair["estimated_opportunity_cost_vs_pair_average"] == 24.9
    driver_two = next(item for item in pair["driver_benchmarks"] if item["driver_id"] == "D2")
    assert driver_two["avg_route_minutes"] == 90.0
    assert driver_two["variance_vs_pair_average_minutes"] == 13.3
    assert driver_two["stop_events_over_threshold"] == 1


def test_address_benchmark_counts_only_stops_strictly_over_threshold():
    config = AddressBenchmarkConfig(
        period_days=30,
        stop_threshold_minutes=60,
        minimum_history_samples=1,
    )
    rows = [
        {
            "OrderTrackingID": "151",
            "DriverNo": "D1",
            "pickup_address": "Fort Worth Yard",
            "delivery_address": "Dallas DC",
            "pickup_departure": "2026-05-20T10:00:00Z",
            "delivery_arrival": "2026-05-20T11:00:00Z",
            "stop_minutes": "60",
        },
        {
            "OrderTrackingID": "152",
            "DriverNo": "D2",
            "pickup_address": "Fort Worth Yard",
            "delivery_address": "Dallas DC",
            "pickup_departure": "2026-05-21T10:00:00Z",
            "delivery_arrival": "2026-05-21T11:00:00Z",
            "stop_minutes": "61",
        },
    ]

    dataset = build_address_benchmark_dataset(rows, config=config, now=_now())

    pair = dataset["address_pairs"][0]
    assert pair["stop_threshold_minutes"] == 60
    assert pair["stop_events_over_threshold"] == 1
    assert [order["stop_over_threshold"] for order in pair["recent_orders"]] == [True, False]


def test_address_benchmark_route_filter_builds_prefiltered_watchlist():
    config = AddressBenchmarkConfig(
        period_days=30,
        stop_threshold_minutes=60,
        minimum_history_samples=1,
        cost_per_truck_hour=120.0,
    )
    rows = [
        {
            "OrderTrackingID": "161",
            "DriverNo": "D1",
            "RouteNo": "DFW001",
            "pickup_address": "Dallas Pickup",
            "delivery_address": "Fort Worth Delivery",
            "pickup_departure": "2026-05-20T08:00:00Z",
            "delivery_arrival": "2026-05-20T09:00:00Z",
        },
        {
            "OrderTrackingID": "162",
            "DriverNo": "D2",
            "RouteNo": "DFW001",
            "pickup_address": "Dallas Pickup",
            "delivery_address": "Fort Worth Delivery",
            "pickup_departure": "2026-05-21T08:00:00Z",
            "delivery_arrival": "2026-05-21T10:00:00Z",
        },
        {
            "OrderTrackingID": "163",
            "DriverNo": "D3",
            "RouteNo": "DFW002",
            "pickup_address": "Arlington Pickup",
            "delivery_address": "Dallas Delivery",
            "pickup_departure": "2026-05-21T08:00:00Z",
            "delivery_arrival": "2026-05-21T10:30:00Z",
        },
    ]

    dataset = build_address_benchmark_dataset(
        rows,
        config=config,
        route="DFW 001",
        now=_now(),
    )

    assert dataset["filters"]["route"] == "DFW 001"
    assert dataset["source_authority"].startswith("K1 Group LLC / Xcelerator")
    assert dataset["summary"]["address_pairs"] == 1
    pair = dataset["address_pairs"][0]
    assert pair["routes"] == ["DFW001"]
    assert pair["pickup_address"] == "Dallas Pickup"
    assert pair["opportunity_minutes_vs_pair_average"] == 30.0
    assert pair["recent_orders"][0]["route"] == "DFW001"
    assert pair["source_authority"] == "K1 Group LLC / Xcelerator ReviewOrders rows"


def test_address_benchmark_period_uses_configured_timezone():
    config = AddressBenchmarkConfig(
        period_days=1,
        minimum_history_samples=1,
        timezone="America/Chicago",
    )
    rows = [
        {
            "OrderTrackingID": "175",
            "DriverNo": "D1",
            "pickup_address": "Fort Worth Yard",
            "delivery_address": "Dallas DC",
            "pickup_departure": "2026-05-29T15:00:00Z",
            "delivery_arrival": "2026-05-29T16:00:00Z",
        }
    ]

    dataset = build_address_benchmark_dataset(
        rows,
        config=config,
        now=datetime(2026, 5, 30, 2, tzinfo=timezone.utc),
    )

    assert dataset["period"]["end"] == "2026-05-29"
    assert dataset["summary"]["address_pairs"] == 1
    assert dataset["address_pairs"][0]["recent_orders"][0]["route_date"] == "2026-05-29"


def test_address_benchmark_date_only_values_do_not_shift_to_prior_local_day():
    config = AddressBenchmarkConfig(
        period_days=2,
        minimum_history_samples=1,
        timezone="America/Chicago",
    )
    rows = [
        {
            "OrderTrackingID": "176",
            "DriverNo": "D1",
            "pickup_address": "Fort Worth Yard",
            "delivery_address": "Dallas DC",
            "date": "2026-05-20",
            "route_minutes": "60",
        }
    ]

    dataset = build_address_benchmark_dataset(
        rows,
        config=config,
        now=datetime(2026, 5, 21, 17, tzinfo=timezone.utc),
    )

    assert dataset["period"]["end"] == "2026-05-21"
    assert dataset["summary"]["address_pairs"] == 1
    assert dataset["address_pairs"][0]["recent_orders"][0]["route_date"] == "2026-05-20"


def test_address_benchmark_attaches_configured_voice_and_email_evidence():
    config = AddressBenchmarkConfig(period_days=30, minimum_history_samples=1)
    rows = [
        {
            "OrderTrackingID": "201",
            "DriverNo": "D5",
            "pickup_address": "Aledo Pickup",
            "delivery_address": "Irving Delivery",
            "pickup_departure": "2026-05-24T08:00:00Z",
            "delivery_arrival": "2026-05-24T09:10:00Z",
        }
    ]
    evidence_rows = [
        {
            "evidence_type": "voice_recording",
            "order_id": "201",
            "source_system": "Grasshopper",
            "summary": "Receiver requested a later dock door.",
            "transcript": "Receiver requested a later dock door.",
        },
        {
            "evidence_type": "email",
            "pickup_address": "Aledo Pickup",
            "delivery_address": "Irving Delivery",
            "source_system": "Outlook",
            "subject": "Dock delay",
            "summary": "Email confirms the receiver delay.",
        },
    ]

    dataset = build_address_benchmark_dataset(
        rows,
        evidence_rows=evidence_rows,
        config=config,
        now=_now(),
        source_meta={"evidence": {"status": "healthy", "row_count": 2}},
    )

    evidence = dataset["address_pairs"][0]["evidence"]
    assert evidence["voice_recordings"]["status"] == "matched"
    assert evidence["voice_recordings"]["match_count"] == 1
    assert evidence["voice_recordings"]["matches"][0]["transcript_available"] is True
    assert evidence["emails"]["status"] == "matched"
    assert evidence["emails"]["match_count"] == 1
    assert dataset["evidence_sources"]["status"] == "healthy"


def test_address_benchmark_reports_pending_evidence_config_without_fabricating_matches():
    config = AddressBenchmarkConfig(period_days=30, minimum_history_samples=1)
    rows = [
        {
            "OrderTrackingID": "301",
            "DriverNo": "D7",
            "pickup_address": "Fort Worth",
            "delivery_address": "Houston",
            "pickup_departure": "2026-05-25T08:00:00Z",
            "delivery_arrival": "2026-05-25T13:00:00Z",
        }
    ]

    dataset = build_address_benchmark_dataset(
        rows,
        config=config,
        now=_now(),
        source_meta={
            "evidence": {
                "status": "pending_config",
                "required_config": ["FLEETPULSE_ADDRESS_BENCHMARK_EVIDENCE_PATH"],
            }
        },
    )

    pair = dataset["address_pairs"][0]
    assert pair["evidence"]["voice_recordings"]["status"] == "no_matching_evidence"
    assert pair["evidence"]["emails"]["status"] == "no_matching_evidence"
    assert dataset["evidence_sources"]["required_config"] == [
        "FLEETPULSE_ADDRESS_BENCHMARK_EVIDENCE_PATH"
    ]


def test_address_benchmark_can_read_configured_fabric_warehouse(monkeypatch):
    monkeypatch.setattr(
        service.FabricWarehouseSqlConfig,
        "from_env",
        lambda prefix: SimpleNamespace(configured=True),
    )
    queries: list[str] = []

    def fake_execute_sql_query(_config, query):
        queries.append(query)
        if "FROM sys.objects AS objects" in query and "GROUP BY" in query:
            return [{"table_schema": "dbo", "table_name": "xcelerator_review_orders"}]
        if "SELECT columns.name AS column_name" in query:
            return [
                {"column_name": "order_tracking_id"},
                {"column_name": "driver_no"},
                {"column_name": "pickup_city"},
                {"column_name": "delivery_city"},
                {"column_name": "pickup_target_from"},
                {"column_name": "p_departure"},
                {"column_name": "d_arrival"},
                {"column_name": "grand_total"},
                {"column_name": "driver_pay"},
            ]
        return [
            {
                "order_id": "WH-1",
                "driver_id": "D9",
                "driver_name": "D9",
                "pickup_address": "Fort Worth",
                "delivery_address": "Austin",
                "pickup_departure": "2026-05-20T10:00:00",
                "delivery_arrival": "2026-05-20T13:00:00",
                "revenue": 900,
                "driver_pay": 300,
                "date": "2026-05-20T09:00:00",
            }
        ]

    monkeypatch.setattr(service, "execute_sql_query", fake_execute_sql_query)
    dataset = service.get_address_benchmark_dataset(
        days=30,
        config=AddressBenchmarkConfig(
            xcelerator_source="fabric_warehouse_sql",
            minimum_history_samples=1,
        ),
        now=_now(),
    )

    assert dataset["source_meta"]["xcelerator"]["effective_xcelerator_source"] == "fabric_warehouse_sql"
    assert dataset["source_meta"]["xcelerator"]["row_count"] == 1
    assert dataset["address_pairs"][0]["avg_route_minutes"] == 180.0
    assert any("xcelerator_review_orders" in query for query in queries)


def test_address_benchmark_can_read_xcelerator_ceo_powerbi_watchlist(monkeypatch):
    monkeypatch.setattr(
        service.PowerBIExecuteQueriesConfig,
        "from_env",
        lambda prefix: SimpleNamespace(configured=True),
    )
    queries: list[str] = []

    def fake_execute_dax_query(_config, query):
        queries.append(query)
        return [
            {
                "order_id": "BI-1",
                "driver_id": "D1",
                "driver_name": "D1",
                "route": "DFW001",
                "pickup_address": "Dallas Pickup",
                "delivery_address": "Fort Worth Delivery",
                "pickup_departure": "2026-05-20T08:00:00Z",
                "delivery_arrival": "2026-05-20T09:00:00Z",
                "date": "2026-05-20T08:00:00Z",
                "revenue": 500,
                "driver_pay": 200,
            },
            {
                "order_id": "BI-2",
                "driver_id": "D2",
                "driver_name": "D2",
                "route": "DFW001",
                "pickup_address": "Dallas Pickup",
                "delivery_address": "Fort Worth Delivery",
                "pickup_departure": "2026-05-21T08:00:00Z",
                "delivery_arrival": "2026-05-21T10:00:00Z",
                "date": "2026-05-21T08:00:00Z",
                "revenue": 700,
                "driver_pay": 300,
            },
        ]

    monkeypatch.setattr(service, "execute_dax_query", fake_execute_dax_query)

    dataset = service.get_address_benchmark_dataset(
        route="DFW 001",
        days=30,
        config=AddressBenchmarkConfig(
            xcelerator_source="xcelerator_ceo_powerbi",
            minimum_history_samples=1,
        ),
        now=_now(),
    )

    xcelerator = dataset["source_meta"]["xcelerator"]
    assert xcelerator["effective_xcelerator_source"] == "xcelerator_ceo_powerbi"
    assert xcelerator["source_authority"] == service.CEO_POWERBI_SOURCE_AUTHORITY
    assert xcelerator["duration_basis"].startswith("pickup_target_from")
    assert dataset["source_authority"] == service.CEO_POWERBI_SOURCE_AUTHORITY
    assert dataset["summary"]["address_pairs"] == 1
    pair = dataset["address_pairs"][0]
    assert pair["routes"] == ["DFW001"]
    assert pair["route_minutes_source"] == "Xcelerator CEO Dashboard BI pickup/delivery target window"
    assert pair["opportunity_minutes_vs_pair_average"] == 30.0
    assert pair["recent_orders"][0]["duration_source"] == "xcelerator_target_window"
    assert "'xcelerator_review_orders'[route_no]" in queries[0]
    assert "dfw001" in queries[0]


def test_address_benchmark_reports_ceo_powerbi_config_gap_without_state_fallback(monkeypatch):
    monkeypatch.setattr(
        service.PowerBIExecuteQueriesConfig,
        "from_env",
        lambda prefix: SimpleNamespace(configured=False),
    )

    dataset = service.get_address_benchmark_dataset(
        route="DFW 001",
        days=30,
        config=AddressBenchmarkConfig(
            xcelerator_source="ceo_powerbi",
            minimum_history_samples=1,
        ),
        now=_now(),
    )

    xcelerator = dataset["source_meta"]["xcelerator"]
    assert xcelerator["status"] == "unavailable"
    assert xcelerator["effective_xcelerator_source"] == "xcelerator_ceo_powerbi"
    assert "FLEETPULSE_XCELERATOR_CEO_POWERBI_ACCESS_TOKEN or client credentials" in xcelerator["required_config"]
    assert dataset["summary"]["address_pairs"] == 0
