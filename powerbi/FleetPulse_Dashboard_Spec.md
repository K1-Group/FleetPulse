# FleetPulse Power BI Dashboard Specification

## Purpose

Give operations a read-only Power BI view of fleet status, trip productivity, terminal coverage, and safety risk from FleetPulse/Geotab without changing source-of-truth systems.

## Source Tables

| Table | Grain | Primary use |
| --- | --- | --- |
| FleetPulseOverview | One row per refresh | Executive KPI cards and trip target performance |
| FleetPulseVehicles | One row per vehicle | Vehicle status, contact freshness, map, active fleet table |
| FleetPulseLocations | One row per terminal | Terminal coverage and location scorecards |
| FleetPulseSafetyScores | One row per vehicle per period | Safety ranking, event mix, risk list |
| FleetPulseSnapshot | One row/object per refresh | Audit view and row-count monitoring |

## Page 1 - Executive Overview

Top KPI cards:

- Total Vehicles
- Active Vehicles
- Parked Vehicles
- Offline Vehicles
- Trips Today
- Stops Today
- Miles Today
- Average Trip Duration Hours
- Trips Meeting 12 Hour Target
- Trip Target Attainment %

Main visuals:

- Vehicle Status stacked bar: Active, Idle, Parked, Offline.
- Trip Target gauge: Trips Meeting Target over Total Trips Today.
- Location Coverage table: Location, Vehicle Count, Active, Safety Score.
- Safety Snapshot cards: Average Safety Score, High Risk Vehicles, Total Safety Events.

## Page 2 - Fleet Status

Filters:

- Vehicle status.
- Location name.
- Last contact date.

Visuals:

- Vehicle table: Name, Status, Location, Speed, Last Contact, Odometer KM.
- Map visual: Latitude, Longitude, Name, Status.
- Offline list: Vehicles with status Offline or missing Last Contact.

## Page 3 - Safety

Filters:

- Period days.
- Trend.
- Score band.

Visuals:

- Lowest Safety Scores table: Vehicle, Score, Trend, Event Count.
- Event mix stacked bar: Speeding, Harsh Braking, Harsh Acceleration, Harsh Cornering.
- High risk count: Score below 70.
- Trend summary: Improving, Stable, Declining.

## Page 4 - Terminal Operations

Visuals:

- Terminal scorecard table: Name, Address, Vehicle Count, Active, Safety Score.
- Terminal map: Latitude, Longitude, Vehicle Count.
- Empty terminal flag: Vehicle Count = 0.
- Active concentration: Active by location.

## Operating Rules

- Power BI is read-only.
- FleetPulse is the reporting API layer.
- Geotab remains the source authority for telemetry, location, safety, maintenance, and fleet performance.
- Power BI must not be used to override Geotab or FleetPulse records.
- Any dashboard metric that looks wrong must be traced back to the corresponding FleetPulse endpoint before operational action is taken.

## Quality Checks

Before publishing a new version:

- Run `python3 powerbi/validate_fleetpulse_connections.py`.
- Confirm the snapshot row counts match the endpoint row counts.
- Confirm `projection_mode` is `read_only` on all row-based endpoints.
- Confirm `source_authority` is `Geotab`.
- Confirm the Executive Overview KPI values match `/api/powerbi/overview`.

