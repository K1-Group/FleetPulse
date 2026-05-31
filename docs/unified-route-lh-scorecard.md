# Unified Route/LH Scorecard Surface

FleetPulse exposes the May 23 unified route/LH scorecard as a read-only lane-stability projection at:

- `GET /api/lane-stability/unified-scorecard`

The endpoint reads approved local workbook artifacts and returns route/LH missed-hour revenue, action guidance, 12-hour capacity gap lines, source notes, and source-boundary rules. It does not write to Xcelerator, Geotab, SharePoint, Power BI, Teams, or any workflow system.

## Source Boundary

- Xcelerator remains the operations and financial source for revenue, driver pay, expenses, load lifecycle, dispatch state, and ReviewOrders exports.
- Geotab remains the K1 Logistics Inc source for telemetry, diagnostics, maintenance, and safety. Safety values remain `Not scored` unless live Geotab rows are available.
- FleetPulse renders the workbook as a planning reference only. Missing source rows remain missing or `Not scored`; they are not converted to zero.
- The 12-hour capacity lines are planning artifacts. Green active-stop segments come from the capacity-plan workbook when available, amber gap segments come from workbook gap windows over 60 minutes, and FleetPulse does not calculate injected revenue.

## Workbook Contract

Default local artifact:

- `outputs/lane-stability-2026-05-23/K1_Unified_Route_LH_Scorecard_WE_2026-05-23.xlsx`
- `outputs/lane-stability-2026-05-23/K1_Sales_Capacity_Plan_WE_2026-05-23.xlsx`

Override for deployment or alternate approved artifacts:

- `FLEETPULSE_UNIFIED_ROUTE_LH_SCORECARD_PATH`
- `FLEETPULSE_SALES_CAPACITY_PLAN_PATH`

Expected workbook sheets:

- `Dashboard`
- `Unified Scorecard`
- `Gap Detail`
- `Metric Definitions`
- `Capacity Plan` from the sales-capacity plan workbook, optional but preferred for active stop/work segments

## In-App Surface

The Stability tab now shows:

- Missed-hour revenue totals split by local route vs LH lane.
- Route/LH unit counts and missed hours.
- 12-hour route/LH capacity timelines with green active stop/work spans and amber source gaps over 60 minutes.
- Top route/LH rows ranked by missed-hour revenue.
- Workbook action guidance from `Sales / Relationship Action`.
- Source-boundary/audit notes confirming Xcelerator and Geotab ownership.
