# FleetPulse Power BI Dashboard Package

This folder contains the report assets for the FleetPulse Power BI dashboard. The dashboard is read-only and uses FleetPulse's deployed Power BI endpoints as projections of Geotab source data.

## Built Assets

- `fleetpulse_dashboard.html` - live browser preview dashboard backed by the deployed FleetPulse Power BI endpoints.
- `queries/*.pq` - one Power Query M query per Power BI table.
- `fleetpulse_measures.dax` - recommended DAX measures for the report.
- `FleetPulse_Dashboard_Spec.md` - page layout, visual definitions, and operating rules.
- `validate_fleetpulse_connections.py` - smoke test for all five deployed Power BI endpoints.
- `fleetpulse_connections.pq` - quick reference index for all five connections.

## Live Source

Set this Power BI parameter:

```text
FleetPulseBaseUrl = https://k1-fleetpulse.azurewebsites.net
```

The core Geotab read-only tables are:

| Table | Endpoint |
| --- | --- |
| FleetPulseOverview | `/api/powerbi/overview` |
| FleetPulseLocations | `/api/powerbi/locations` |
| FleetPulseVehicles | `/api/powerbi/vehicles` |
| FleetPulseSafetyScores | `/api/powerbi/safety-scores?days=7` |
| FleetPulseSnapshot | `/api/powerbi/fleetpulse-snapshot?days=7` |

The lane stability Xcelerator projection adds these read-only tables:

| Table | Endpoint |
| --- | --- |
| LaneStabilityCompany | `/api/powerbi/lane-stability/company?days=7` |
| LaneStabilityByService | `/api/powerbi/lane-stability/by-service?days=7` |
| LaneStabilityLanes | `/api/powerbi/lane-stability/lanes?days=7` |
| LaneStabilityRoutes | `/api/powerbi/lane-stability/routes?days=7` |
| LaneStabilityDaily | `/api/powerbi/lane-stability/daily?days=7` |
| LaneStabilityTrend | `/api/powerbi/lane-stability/trend?days=7` |
| LaneStabilitySnapshot | `/api/powerbi/lane-stability-snapshot?days=7` |

The operating cost projection adds weekly true-cost reporting. FleetPulse
calculates true cost only when every source feed is healthy; otherwise the
tables retain known costs and leave true CPM/hour fields blank.

| Table | Endpoint |
| --- | --- |
| OperatingCostSummary | `/api/powerbi/operating-cost/summary?start=<yyyy-mm-dd>&end=<yyyy-mm-dd>` |
| OperatingCostWeekly | `/api/powerbi/operating-cost/weekly?start=<yyyy-mm-dd>&end=<yyyy-mm-dd>` |

## Build The Power BI Report

1. Open Power BI Desktop.
2. Create a text parameter named `FleetPulseBaseUrl` with value `https://k1-fleetpulse.azurewebsites.net`.
3. For each file in `powerbi/queries`, create a Blank Query, open Advanced Editor, paste the query, and name the table to match the file name.
4. Add the measures from `fleetpulse_measures.dax` to the model.
5. Build the report pages from `FleetPulse_Dashboard_Spec.md`.
6. Publish to the target Power BI workspace and configure scheduled refresh.

## Refresh Settings

- Recommended refresh interval: every 15 minutes during operations.
- Authentication mode: Anonymous/Web for the public read-only FleetPulse projection endpoint, or the future managed service identity gateway if FleetPulse auth is tightened.
- Do not write back to Geotab, Xcelerator, or FleetPulse from Power BI.

## Lane Stability Source Configuration

FleetPulse can score lane stability from a live JSON/CSV/XLSX ReviewOrders feed
or from a precomputed lane stability JSON payload. Xcelerator remains the source
of truth for orders, revenue, driver pay, and route assignments; FleetPulse only
projects analytics rows for Power BI.

Recommended live feed variables:

```bash
FLEETPULSE_LANE_STABILITY_ORDER_FEED_URL=https://example.internal/revieworders/latest
FLEETPULSE_LANE_STABILITY_ORDER_FEED_API_KEY=
FLEETPULSE_LANE_STABILITY_BASELINE_ORDER_FEED_URL=https://example.internal/revieworders/baseline
FLEETPULSE_LANE_STABILITY_BASELINE_ORDER_FEED_API_KEY=
FLEETPULSE_LANE_STABILITY_EXCLUDED_SCORING_SERVICES=ATL-ShipBob
FLEETPULSE_LANE_STABILITY_EXCLUDED_SCORING_REF_PATTERNS=pay ticket,route ticket,tonu,service-only
```

Fallback payload variables for the current workbook-style JSON contract:

```bash
FLEETPULSE_LANE_STABILITY_PAYLOAD_URL=
FLEETPULSE_LANE_STABILITY_PAYLOAD_PATH=
FLEETPULSE_LANE_STABILITY_BASELINE_PAYLOAD_URL=
FLEETPULSE_LANE_STABILITY_BASELINE_PAYLOAD_PATH=
```

Revenue methodology:

- Company KPIs use the Xcelerator footer total when present, matching the TMS report total.
- Lane scoring excludes configured pay-ticket/service-only rows and excluded services, but those rows still remain in company revenue.
- Stable coverage is the primary-driver run count divided by total runs for the lane.

## Operating Cost Source Configuration

Operating cost charts use source-owned facts only:

- Geotab Data Connector: miles, drive hours, idle hours, trips.
- AtoB import or SharePoint sync: approved fuel/DEF card cost.
- Xcelerator ReviewOrders feed: driver pay.
- QuickBooks Online export/feed: insurance and other company expenses.

Required variables for full true cost:

```bash
FLEETPULSE_ATOB_FUEL_STATE_PATH=/home/data/fleetpulse_atob_fuel_expenses.json
FLEETPULSE_LANE_STABILITY_ORDER_FEED_URL=
FLEETPULSE_LANE_STABILITY_ORDER_FEED_API_KEY=
FLEETPULSE_QBO_EXPENSE_FEED_URL=
FLEETPULSE_QBO_EXPENSE_FEED_PATH=
FLEETPULSE_QBO_EXPENSE_FEED_API_KEY=
FLEETPULSE_QBO_INSURANCE_ACCOUNT_PATTERNS=insurance
FLEETPULSE_QBO_EXCLUDED_ACCOUNT_PATTERNS=accounts receivable,atob,carrier,cogs,contractor,cost of goods sold,diesel,driver pay,driver settlement,factoring,freight in,fuel,income,payroll,revenue,sales,wages
```

QBO expense feeds can be CSV or JSON. FleetPulse excludes fuel and driver-pay
accounts by default to avoid double-counting AtoB and Xcelerator.

## Validation

Run this before publishing or after API changes:

```bash
python3 powerbi/validate_fleetpulse_connections.py
```

The script verifies:

- HTTP 200 for all configured fleet and lane-stability endpoints.
- Non-empty overview, vehicles, and safety tables.
- `projection_mode = read_only`.
- `source_authority = Geotab` for fleet tables and `K1 Group LLC / Xcelerator` for lane stability tables.
- Snapshot row counts align with the individual endpoint counts.

## Publish To Power BI Workspace

The API publisher creates/refreshes a Push semantic model in the selected Power BI workspace, pushes the live FleetPulse rows, creates a dashboard shell, and publishes a native PBIR report bound to the new model.

Report cloning is intentionally disabled by default because cloned reports can retain old field bindings. Enable it only when the source report schema is confirmed compatible.

Default workspace:

```text
K1 Operations Hub
Workspace ID: b801f80d-5303-4121-abd1-1163639ef58b
```

Run:

```bash
python3 powerbi/publish_to_powerbi.py
```

Optional environment overrides:

```bash
POWERBI_WORKSPACE_ID=<workspace-guid>
POWERBI_WORKSPACE_NAME="Workspace Name"
POWERBI_DATASET_NAME="FleetPulse Live Operations"
POWERBI_DASHBOARD_NAME="FleetPulse Live Operations Dashboard"
POWERBI_NATIVE_REPORT_NAME="FleetPulse Live Operations Native Report"
POWERBI_CLONE_REPORT_NAME="FleetPulse Live Operations Report"
POWERBI_SOURCE_REPORT_ID=<existing-report-guid>
POWERBI_ENABLE_CLONE=false
```

Authentication:

- Preferred local operator path: Azure CLI signed in as a Power BI workspace contributor.
- Alternative automation path: set `POWERBI_ACCESS_TOKEN` from a secure CI identity.
- Do not commit or print Power BI tokens.
