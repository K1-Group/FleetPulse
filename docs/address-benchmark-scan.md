# Address Benchmark Scan

FleetPulse exposes a read-only historical pickup/delivery scan at:

`GET /api/address-benchmarks`

Optional query parameters:

- `pickup`: pickup address or city substring filter
- `delivery`: delivery address or city substring filter
- `days`: history window, 1-730 days

## Source Boundaries

- Xcelerator ReviewOrders rows remain authoritative for pickup/delivery addresses, lifecycle timestamps, revenue, and driver pay.
- FleetPulse computes pickup-to-delivery averages, driver variance, and opportunity minutes as a projection only.
- Voice recordings and emails are attached only when a configured read-only evidence file exists. Missing recordings, transcripts, or emails are reported as missing or pending config; they are not fabricated.
- The dashboard displays configured evidence subjects/summaries, source system, order match, transcript availability, and evidence links when those fields are present. FleetPulse does not transcribe recordings in this projection; transcripts must come from the configured evidence feed.
- The `decision_summary` groups company action, driver action, and evidence action as read-only planning guidance; it does not authorize payroll, dispatch, Geotab, or Xcelerator writes.
- Driver comparison rows include visible action guidance so benchmark drivers, drivers above the lane average, and evidence-driven dwell reviews can be handled before changing coaching, incentives, or route expectations.
- `stop_threshold_minutes` defaults to 60 and is applied only to configured stop/dwell evidence fields such as `stop_minutes`, `idle_minutes`, `dwell_minutes`, or `geotab_stop_minutes`.
- When present in the read-only route rows, `stop_address` or `stop_geofence` details are displayed with the matching >60m stop. Missing stop locations remain blank; FleetPulse does not infer or geocode them.

## Required Configuration

Historical Xcelerator rows:

- `FLEETPULSE_XCELERATOR_WAREHOUSE_SQL_*` for the read-only Fabric/Xcelerator warehouse, or
- `FLEETPULSE_XCELERATOR_REVIEW_ORDERS_STATE_PATH` for the local ReviewOrders state fallback

Optional benchmark tuning:

- `FLEETPULSE_ADDRESS_BENCHMARK_XCELERATOR_SOURCE` (`auto`, `fabric_warehouse_sql`, or `review_orders_state`)
- `FLEETPULSE_ADDRESS_BENCHMARK_PERIOD_DAYS`
- `FLEETPULSE_ADDRESS_BENCHMARK_STOP_THRESHOLD_MINUTES`
- `FLEETPULSE_ADDRESS_BENCHMARK_MIN_HISTORY_SAMPLES`
- `FLEETPULSE_ADDRESS_BENCHMARK_MAX_PAIRS`
- `FLEETPULSE_ADDRESS_BENCHMARK_MAX_SOURCE_ROWS`
- `FLEETPULSE_ADDRESS_BENCHMARK_COST_PER_TRUCK_HOUR`

Optional voice/email evidence annotations:

- `FLEETPULSE_ADDRESS_BENCHMARK_EVIDENCE_PATH`

Useful optional route columns for long-stop location proof include `stop_address`, `long_stop_address`, `geotab_stop_address`, `stop_geofence`, `geofence_name`, and `site_name`.

The evidence file may be JSON, JSONL, CSV, TSV, pipe-delimited, or semicolon-delimited. Rows can match by `order_id`/`load_id`/`reference_id` or pickup/delivery pair. Driver-only evidence is treated as too broad for address-pair proof and is not attached to a lane. Supported evidence types include `voice_recording`, `recording`, `call`, `voicemail`, `email`, and `outlook`.
Useful optional columns include `source_system`, `service`, `platform`, `subject`, `title`, `summary`, `snippet`, `body_preview`, `transcript`, `transcription`, `source_uri`, `webLink`, `recording_link`, `message_url`, `sharepoint_url`, `teams_url`, `drive_url`, `occurred_at`, `received_at`, `sent_at`, `driver_id`, `order_id`, `load_id`, `pickup_address`, and `delivery_address`.
Evidence links are rendered only when the configured URI is `http` or `https`; unsafe or local URI schemes are suppressed.
