# Address Benchmark Scan

FleetPulse exposes a read-only historical pickup/delivery scan at:

`GET /api/address-benchmarks`

The frontend surface is available from the FleetPulse left navigation as
`Benchmarks`.

No-server UI smoke check: `cd frontend && npm run verify:address-benchmark-ui`.

Optional query parameters:

- `pickup`: pickup address or city substring filter
- `delivery`: delivery address or city substring filter
- `route`: Xcelerator route/lane identifier filter, used by the Stability gap-detail handoff
- `days`: history window, 1-730 days

## Source Boundaries

- Xcelerator ReviewOrders rows remain authoritative for pickup/delivery addresses, lifecycle timestamps, target windows, revenue, and driver pay.
- The preferred Stability handoff source is the Xcelerator CEO Dashboard Power BI semantic model when `FLEETPULSE_ADDRESS_BENCHMARK_XCELERATOR_SOURCE=xcelerator_ceo_powerbi` is configured with read-only Power BI credentials.
- FleetPulse computes pickup-to-delivery averages, driver variance, and opportunity minutes as a projection only.
- Voice recordings and emails are attached only when a configured read-only evidence file exists. Missing recordings, transcripts, or emails are reported as missing or pending config; they are not fabricated.
- `stop_threshold_minutes` defaults to 60 and is applied only to configured stop/dwell evidence fields such as `stop_minutes`, `idle_minutes`, `dwell_minutes`, or `geotab_stop_minutes`.
- Stability gap rows link to `#address-benchmarks?route=<route>&days=180`; the watchlist only shows pickup/delivery pairs present in Xcelerator-derived benchmark rows and does not infer addresses from the workbook.

## Required Configuration

Historical Xcelerator rows:

- `FLEETPULSE_ADDRESS_BENCHMARK_XCELERATOR_SOURCE=xcelerator_ceo_powerbi` plus `FLEETPULSE_XCELERATOR_CEO_POWERBI_*` for the read-only Xcelerator CEO Dashboard BI semantic model,
- `FLEETPULSE_XCELERATOR_WAREHOUSE_SQL_*` for the read-only Fabric/Xcelerator warehouse, or
- `FLEETPULSE_XCELERATOR_REVIEW_ORDERS_STATE_PATH` for the local ReviewOrders state fallback

Optional benchmark tuning:

- `FLEETPULSE_ADDRESS_BENCHMARK_XCELERATOR_SOURCE` (`auto`, `xcelerator_ceo_powerbi`, `fabric_warehouse_sql`, or `review_orders_state`)
- `FLEETPULSE_ADDRESS_BENCHMARK_PERIOD_DAYS`
- `FLEETPULSE_ADDRESS_BENCHMARK_STOP_THRESHOLD_MINUTES`
- `FLEETPULSE_ADDRESS_BENCHMARK_MIN_HISTORY_SAMPLES`
- `FLEETPULSE_ADDRESS_BENCHMARK_MAX_PAIRS`
- `FLEETPULSE_ADDRESS_BENCHMARK_MAX_RECENT_ORDERS_PER_PAIR`
- `FLEETPULSE_ADDRESS_BENCHMARK_MAX_SOURCE_ROWS`
- `FLEETPULSE_ADDRESS_BENCHMARK_TIMEZONE` controls reporting-period day boundaries
- `FLEETPULSE_ADDRESS_BENCHMARK_COST_PER_TRUCK_HOUR`

Optional voice/email evidence annotations:

- `FLEETPULSE_ADDRESS_BENCHMARK_EVIDENCE_PATH`

The evidence file may be JSON, JSONL, CSV, TSV, pipe-delimited, or semicolon-delimited. Rows can match by `order_id`, pickup/delivery pair, or driver. Supported evidence types include `voice_recording`, `recording`, `call`, `voicemail`, `email`, and `outlook`.

## Seat Access

When FleetPulse Entra seat enforcement is enabled, `/api/address-benchmarks`
maps to the `address-benchmarks` tab. The default read-only seat contract grants
that tab to Executive Command, Revenue Manager, Operations Manager, and Fleet &
Compliance Manager seats.
