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

The five read-only tables are:

| Table | Endpoint |
| --- | --- |
| FleetPulseOverview | `/api/powerbi/overview` |
| FleetPulseLocations | `/api/powerbi/locations` |
| FleetPulseVehicles | `/api/powerbi/vehicles` |
| FleetPulseSafetyScores | `/api/powerbi/safety-scores?days=7` |
| FleetPulseSnapshot | `/api/powerbi/fleetpulse-snapshot?days=7` |

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
- Do not write back to Geotab or FleetPulse from Power BI.

## Validation

Run this before publishing or after API changes:

```bash
python3 powerbi/validate_fleetpulse_connections.py
```

The script verifies:

- HTTP 200 for all five endpoints.
- Non-empty overview, vehicles, and safety tables.
- `projection_mode = read_only`.
- `source_authority = Geotab`.
- Snapshot row counts align with the individual endpoint counts.

