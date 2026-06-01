# Unified Route/LH Scorecard Surface

FleetPulse exposes the May 23 unified route/LH scorecard as a read-only lane-stability projection at:

- `GET /api/lane-stability/unified-scorecard`

The endpoint reads an approved local workbook artifact and returns route/LH missed-hour revenue, workbook gap-detail evidence, action guidance, source notes, and source-boundary rules. It does not write to Xcelerator, Geotab, SharePoint, Power BI, Teams, or any workflow system.

## Source Boundary

- Xcelerator remains the operations and financial source for revenue, driver pay, expenses, load lifecycle, dispatch state, and ReviewOrders exports.
- Geotab remains the K1 Logistics Inc source for telemetry, diagnostics, maintenance, and safety. Safety values remain `Not scored` unless live Geotab rows are available.
- FleetPulse renders the workbook as a planning reference only. Missing source rows remain missing or `Not scored`; they are not converted to zero.

## Workbook Contract

Default local artifact:

- `outputs/lane-stability-2026-05-23/K1_Unified_Route_LH_Scorecard_WE_2026-05-23.xlsx`

Override for deployment or alternate approved artifacts:

- `FLEETPULSE_UNIFIED_ROUTE_LH_SCORECARD_PATH`
- `FLEETPULSE_UNIFIED_ROUTE_LH_SCORECARD_PRIOR_PATH` for optional prior-period KPI deltas

Expected workbook sheets:

- `Dashboard`
- `Unified Scorecard`
- `Gap Detail`
- `Metric Definitions`

## In-App Surface

The Stability tab now shows:

- Missed-hour revenue totals split by local route vs LH lane.
- Route/LH unit counts and missed hours.
- Top route/LH rows ranked by missed-hour revenue.
- Exact `Gap Detail` capacity windows with route, date, gap type, paid-window basis, workbook row, missed hours, and missed-hour revenue.
- Gap evidence grouped by route and gap type, including repeated local route windows such as `DFW 002` and `DFW 001` when present in the workbook.
- Gap routes and repeated gap rows link to the read-only address benchmark watchlist with `route=<Route/LH>` and `days=180`; pickup/delivery pairs appear only when Xcelerator-derived benchmark rows contain matching route evidence.
- Workbook action guidance from `Sales / Relationship Action`.
- Mixed chart views for missed-hour revenue by action bucket and top route/LH.
- KPI trend capture cards when an approved prior workbook is configured.
- Copy-summary and print/PDF capture controls for local review packets.
- Source-boundary/audit notes confirming Xcelerator and Geotab ownership.
