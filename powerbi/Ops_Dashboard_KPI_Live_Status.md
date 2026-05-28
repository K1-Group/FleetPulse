# FleetPulse Ops Dashboard KPI Live Status

Validated at: `2026-05-13T00:27:01Z`

Command:

```bash
python3 powerbi/validate_ops_dashboard_kpis.py
```

Base URL:

```text
https://k1-fleetpulse.azurewebsites.net
```

## Certification Summary

| Role | Status | Checks | Certification decision |
| --- | --- | ---: | --- |
| Fleet Ops Manager | needs_attention | 6/6 passed | Core Geotab KPI path is live. Do not certify frontend trend/sparkline visuals until historical trend data backs them. |
| Track & Trace | needs_attention | 2/2 passed | Geotab/XTRA trailer visibility is live. Custody remains inferred until Xcelerator dispatch assignment confirms tractor, driver, load, and trailer. |
| Dispatch | blocked | 0/2 passed | Do not certify Dispatch KPIs until Xcelerator route SLA feed and Power Automate approval flow are healthy. |
| Sales | blocked | 2/7 passed | Lane-stability API routes now return JSON, but the Xcelerator feed is not configured. Do not certify Sales KPIs until feed status is healthy and revenue reconciles to Xcelerator. |

Overall status: `blocked`

Power BI publish status:

| Artifact | Status |
| --- | --- |
| Workspace | `K1 Operations Hub` |
| Dataset | `FleetPulse Live Operations` refreshed |
| Dashboard | `FleetPulse Live Operations Dashboard` available |
| Native report | `FleetPulse Live Operations Native Report` available |
| Published tables | `FleetPulseOverview`, `FleetPulseLocations`, `FleetPulseVehicles`, `FleetPulseSafetyScores` |
| Lane-stability tables | Not published because Xcelerator feed is `awaiting_feed` |

Power BI URLs:

- Dashboard: https://app.powerbi.com/groups/b801f80d-5303-4121-abd1-1163639ef58b/dashboards/b4e7e44d-4306-4415-8861-35ecbd549ace
- Native report: https://app.powerbi.com/groups/b801f80d-5303-4121-abd1-1163639ef58b/reports/1cc676e5-3be8-46d8-987d-d040cfa0a8ce

Metric wording note as of 2026-05-27: the Fleet Ops stop count is labeled `Stops >60m` and remains backed by `total_stops_today`.

## Passing Areas

### Fleet Ops Manager

Passed checks:

- `dashboard_overview`
- `powerbi_overview`
- `powerbi_vehicles`
- `powerbi_locations`
- `powerbi_safety_scores`
- `powerbi_fleetpulse_snapshot`

Certified source authority:

```text
Geotab
```

Operational use:

- Vehicle status counts
- Trips, Stops >60m, miles, and average trip duration
- Power BI overview, vehicles, locations, and safety projections
- Read-only fleet telemetry for Fleet Ops Manager review

Remaining control:

- Frontend KPI trend arrows and sparklines must stay informational unless backed by historical endpoint data.

### Track & Trace

Passed checks:

- `control_tower_trailers`
- `control_tower_trailers_live`

Certified source authorities:

```text
K1 Logistics Inc / Geotab
Outlook / XTRA Lease
```

Operational use:

- Trailer GPS active/inactive status
- XTRA geofence event recency
- Trailer live tracking and custody confidence labels

Remaining control:

- Custody must remain labeled as inferred until Xcelerator assignment feed is live.
- Driver identity can remain blank when no recent Geotab trip driver is attached to the nearby tractor.

## Blocked Areas

### Dispatch

Failed checks:

- `control_tower_attention_dispatch_feed`
  - Actual status: `warning`
  - Detail: Xcelerator event feed URL is configured, but the FleetPulse event adapter is not live yet.
- `control_tower_power_automate_dispatch_flow`
  - Actual status: `awaiting_feed`
  - Detail: Awaiting `FLEETPULSE_POWER_AUTOMATE_FLOW_URL`.

Required before certification:

- Deploy or enable the Xcelerator dispatch event adapter.
- Add route SLA, load assignment, exception ownership, and contract blocker projections.
- Configure `FLEETPULSE_POWER_AUTOMATE_FLOW_URL`.
- Verify approval queue fields: owner, claimant, recommender, approver, timestamp, and approval reference.

### Sales

Failed checks:

- `lane_stability_by_service`
- `lane_stability_lanes`
- `lane_stability_routes`
- `lane_stability_daily`
- `lane_stability_trend`

Passing checks:

- `lane_stability_company`
- `lane_stability_snapshot`

Observed blocker:

```text
Lane stability endpoints return JSON, but company feed_status is awaiting_feed.
feed_message = Lane stability feed is not configured.
total_revenue_source = no_feed.
```

Required before certification:

- Configure current and baseline Xcelerator order feeds.
- Verify lane-stability company `feed_status = healthy`.
- Verify lane-stability tables return detail rows for the reporting period.
- Confirm `source_authority = K1 Group LLC / Xcelerator`.
- Reconcile `LaneStabilityCompany[total_revenue]` to the Xcelerator footer total for the same period.

## Next Execution Steps

1. Keep Fleet Ops Manager and Track & Trace pages behind verified/inferred labels.
2. Wire Xcelerator dispatch adapter and Power Automate approval URL.
3. Configure the Xcelerator current and baseline lane-stability feeds in Azure App Settings.
4. Re-run:

```bash
python3 powerbi/validate_ops_dashboard_kpis.py --json
python3 powerbi/validate_ops_dashboard_kpis.py --role fleet_ops_manager --role track_trace --allow-needs-attention
python3 powerbi/validate_fleetpulse_connections.py
```

5. Publish only pages with `verified` or explicitly labeled `needs_attention` status; never publish `blocked` role pages as green.
