# FleetPulse Ops Dashboard KPI Verification Plan

## Purpose

Build a role-based operations dashboard that lets Fleet Ops Manager, Track & Trace, Dispatch, and Sales teams act from verified KPIs without crossing source-of-truth boundaries.

Power BI remains read-only. FleetPulse projects verified analytics rows. Geotab, XTRA Lease, Xcelerator, QuickBooks, SharePoint, Power Automate, Teams, and Twilio stay authoritative only for the domains they own.

## Source Authority Rules

| Domain | Authority | FleetPulse use |
| --- | --- | --- |
| Vehicle GPS, status, mileage, trip activity, safety, maintenance, faults | Geotab / K1 Logistics Inc | Read-only fleet telemetry, map, safety, maintenance, and performance KPIs |
| Trailer GPS | Geotab trailer devices / K1 Logistics Inc | Read-only trailer position and last-contact KPIs |
| Trailer lease, yard, gate, and event notices | XTRA Lease mailbox feed | Read-only trailer event references and custody context |
| Load lifecycle, dispatch assignment, route SLA, customer/order state | Xcelerator / K1 Group LLC | Read-only operational control KPIs and exception queues |
| Revenue, driver pay, expenses, contracts, lane stability | Xcelerator / K1 Group LLC | Read-only Sales and margin/lane-performance KPIs |
| AP/AR/cash position | QuickBooks / K1 Group LLC | Read-only finance KPIs when enabled |
| Audit logs and exception evidence | SharePoint or centralized logging | Durable outcome and approval trail |
| Workflow approvals and notifications | Power Automate, Teams, Twilio | Orchestration and alerting only; no source-of-truth ownership |

## Role KPI Matrix

### Fleet Ops Manager

| KPI | Source authority | Endpoint/table | Verification gate |
| --- | --- | --- | --- |
| Total, active, idle, parked, offline vehicles | Geotab | `/api/dashboard/overview`, `/api/powerbi/overview`, `FleetPulseOverview` | Values match between dashboard and Power BI overview for one refresh window |
| Trips today, stops today, miles today, average trip hours | Geotab | `/api/dashboard/overview`, `/api/powerbi/overview` | Non-empty live Geotab projection; `source_authority = Geotab`; no fabricated trip rows |
| 12-hour trip target attainment | Geotab + FleetPulse projection | `FleetPulseOverview` | Target numerator and denominator reconcile to trip session rows |
| Vehicle map and last contact freshness | Geotab | `/api/powerbi/vehicles`, `FleetPulseVehicles` | Vehicle count equals scoped Geotab device count; stale/offline count exposed |
| Safety score, high-risk vehicles, event mix | Geotab | `/api/powerbi/safety-scores`, `FleetPulseSafetyScores` | Period filter applied; score rows include event mix and read-only projection metadata |
| Terminal coverage and active concentration | Geotab | `/api/powerbi/locations`, `FleetPulseLocations` | Location row counts reconcile to scoped vehicles |
| Maintenance and fault exposure | Geotab | Future maintenance/fault projection | Only show after fault and maintenance endpoints return live, scoped Geotab data |

### Track & Trace

| KPI | Source authority | Endpoint/table | Verification gate |
| --- | --- | --- | --- |
| Live vehicle position | Geotab | `/api/powerbi/vehicles`, map visual | Latitude/longitude, speed, bearing, and last contact are present for active devices |
| Trailer GPS active/inactive | Geotab trailer devices | `/api/control-tower/trailers/live` | Trailer GPS feed healthy; active/inactive counts present |
| XTRA trailer event count and last email received | XTRA Lease mailbox | `/api/control-tower/trailers`, `/api/control-tower/trailers/live` | `last_email_received` updates after ingestion; duplicate emails ignored by idempotency key |
| Custody candidate vehicle/driver | Geotab proximity + XTRA reference | `/api/control-tower/trailers/live` | Label as inferred until Xcelerator dispatch assignment confirms tractor, driver, load, and trailer |
| Yard/geofence event volume | XTRA + Geotab | `/api/control-tower/trailers` | Event rows include source, trailer id, event time, yard/location, and idempotency key |
| Unassigned trailer count | Geotab + Xcelerator dispatch reference | Future dispatch-enriched trailer projection | Only certify after Xcelerator assignment feed is live |

### Dispatch

| KPI | Source authority | Endpoint/table | Verification gate |
| --- | --- | --- | --- |
| Active loads by status | Xcelerator | Future `/api/control-tower/dispatch` or Power BI dispatch table | Xcelerator event adapter live; counts reconcile to ReviewOrders/load status source |
| Driver, tractor, trailer, and load assignment | Xcelerator | Dispatch projection + trailer live projection | Assignment is a reference from Xcelerator, not overwritten from GPS inference |
| Route SLA exceptions | Xcelerator | `/api/control-tower/attention` plus dispatch feed | Route SLA feed healthy; zero exceptions only trusted when feed status is healthy |
| Approval queue and owner/claim state | Xcelerator + Power Automate | `/api/control-tower/agents`, dispatch approval flow | Each item has owner, claimant, recommender, approver, timestamp, and approval reference |
| Paused communications and escalation state | Xcelerator + Twilio/Teams logs | Dispatch exception table | Idempotency key and delivery callback status captured for every outbound notification |
| Contract validation blockers | Xcelerator contract layer | Future contract validation projection | No load progression KPI is green unless contract id, version, rules, docs, and approvals are present |

### Sales

| KPI | Source authority | Endpoint/table | Verification gate |
| --- | --- | --- | --- |
| Xcelerator total revenue | Xcelerator | `/api/powerbi/lane-stability/company`, `LaneStabilityCompany` | JSON endpoint deployed; total reconciles to Xcelerator footer total for same period |
| Team-subset revenue | Xcelerator | `LaneStabilityCompany` | Scoring exclusions do not remove rows from company revenue |
| Weighted stable coverage percent | Xcelerator order/driver/route data | `LaneStabilityCompany`, `LaneStabilityByService` | Stable coverage formula reviewed and period-bound |
| Critical, at-risk, and cross-route lanes | Xcelerator | `LaneStabilityLanes`, `LaneStabilityRoutes`, `LaneStabilityTrend` | Lane counts reconcile across company, service, lane, route, and trend tables |
| Revenue by service and lane | Xcelerator | `LaneStabilityByService`, `LaneStabilityLanes` | Service/lane filters use Xcelerator source fields only |
| Better/worse lane trends | Xcelerator current + baseline feed | `LaneStabilityTrend` | Baseline feed configured; current and baseline periods are explicit |
| Customer/order growth and pipeline | Xcelerator CRM/orders | Future Sales projection | Do not publish until partner/customer contract ownership is mapped |

## Dashboard Pages

1. Fleet Operations
   - Audience: Fleet Ops Manager.
   - Contents: vehicle status, trips, stops, miles, trip target attainment, terminal coverage, safety snapshot, stale/offline list.
   - Certification rule: green only when Geotab endpoint row counts reconcile and every exported row has `projection_mode = read_only`.

2. Track & Trace
   - Audience: Track & Trace team.
   - Contents: vehicle map, trailer map, GPS active/inactive, XTRA event recency, custody candidates, unassigned trailers, stale trailer contacts.
   - Certification rule: custody must display `inferred` until Xcelerator assignment confirms tractor/driver/load/trailer.

3. Dispatch Control
   - Audience: Dispatch and operations leadership.
   - Contents: active loads, route SLA risk, approval queue, contract blockers, paused communications, exception ownership, escalation status.
   - Certification rule: no dispatch KPI is green until the Xcelerator event adapter and Power Automate approval flow are healthy.

4. Sales and Lane Stability
   - Audience: Sales and executive operations.
   - Contents: total revenue, team-subset revenue, weighted stable coverage, critical lanes, at-risk lanes, cross-route lanes, service heatmap, better/worse lanes.
   - Certification rule: lane-stability endpoints must return JSON, source authority must be `K1 Group LLC / Xcelerator`, and revenue must reconcile to Xcelerator.

5. Data Quality and Audit
   - Audience: Systems, BI, and managers.
   - Contents: feed status, row counts, last refresh, last successful ingestion, source authority, projection mode, alert status.
   - Certification rule: every page must expose stale, awaiting-feed, or failed state instead of silently hiding missing source data.

## Implementation Phases

### Phase 1 - KPI Contract and Labels

- Freeze KPI definitions, source authority, endpoint, and acceptance gate for each role.
- Add `verified`, `awaiting_feed`, `inferred`, and `failed` labels to dashboard/Power BI metadata.
- Remove or relabel static trend/sparkline visuals unless they are backed by historical endpoint data.

### Phase 2 - Fleet Ops and Track & Trace Certification

- Validate Geotab overview, vehicles, locations, and safety endpoints.
- Validate XTRA ingestion recency and duplicate suppression.
- Validate trailer live merge with GPS active/inactive counts and custody confidence labels.
- Publish only verified fleet and trace KPIs.

### Phase 3 - Dispatch Feed Activation

- Deploy or enable the Xcelerator dispatch event adapter.
- Wire `FLEETPULSE_POWER_AUTOMATE_FLOW_URL` for approval/visibility flow.
- Add route SLA, assignment, exception ownership, and contract blocker projections.
- Require owner, claim, recommender, approver, approval reference, and timestamp on every dispatch exception.

### Phase 4 - Sales and Lane Stability Activation

- Deploy lane-stability Power BI endpoints to production.
- Configure Xcelerator current and baseline order feeds.
- Reconcile Xcelerator total revenue, team-subset revenue, service revenue, and lane revenue.
- Publish lane stability pages only after production endpoints return JSON and validation passes.

### Phase 5 - Observability and Alerting

- Log each feed run, KPI refresh, ingestion result, duplicate suppression, and critical failure.
- Store structured logs in SharePoint or centralized logging.
- Alert Teams/SMS on critical feed failures, stale XTRA ingestion, Xcelerator dispatch feed failure, lane-stability reconciliation failure, and Power BI validation failure.

## Live Verification Checklist

Run before each dashboard publish:

```bash
python3 powerbi/validate_ops_dashboard_kpis.py
python3 powerbi/validate_fleetpulse_connections.py
```

Required checks:

- `/api/health` returns healthy.
- `/api/dashboard/overview` and `/api/powerbi/overview` reconcile for the same refresh window.
- `/api/powerbi/fleetpulse-snapshot` row counts match overview, locations, vehicles, and safety endpoints.
- `/api/control-tower/trailers` shows a recent `last_email_received`.
- `/api/control-tower/trailers/live` returns trailer GPS and XTRA merge rows with custody confidence.
- `/api/control-tower/attention` feed statuses are inspected before interpreting zero exceptions.
- `/api/control-tower/agents` shows Power Automate dispatch approval flow healthy before Dispatch KPIs are certified.
- `/api/powerbi/lane-stability/company` returns JSON, not the frontend HTML shell.
- All Power BI rows expose `projection_mode = read_only`.
- Fleet rows expose `source_authority = Geotab`.
- Lane-stability rows expose `source_authority = K1 Group LLC / Xcelerator`.

## Required Configuration

### Geotab and Fleet Scope

```bash
GEOTAB_SERVER=
GEOTAB_USERNAME=
GEOTAB_PASSWORD=
GEOTAB_DATABASE=
FLEETPULSE_ALLOWED_DEVICE_GROUP_IDS=
FLEETPULSE_TRAILER_GROUP_IDS=
```

### XTRA Lease Mailbox Ingestion

```bash
XTRA_GRAPH_TENANT_ID=
XTRA_GRAPH_CLIENT_ID=
XTRA_GRAPH_CLIENT_SECRET=
XTRA_MAILBOX_USER_ID=
XTRA_MAIL_FOLDER_ID=
XTRA_LOOKBACK_HOURS=
XTRA_INGESTION_IDEMPOTENCY_SALT=
```

### Xcelerator Dispatch and Sales

```bash
FLEETPULSE_XCELERATOR_EVENT_FEED_URL=
FLEETPULSE_XCELERATOR_EVENT_FEED_API_KEY=
FLEETPULSE_LANE_STABILITY_ORDER_FEED_URL=
FLEETPULSE_LANE_STABILITY_ORDER_FEED_API_KEY=
FLEETPULSE_LANE_STABILITY_BASELINE_ORDER_FEED_URL=
FLEETPULSE_LANE_STABILITY_BASELINE_ORDER_FEED_API_KEY=
FLEETPULSE_LANE_STABILITY_EXCLUDED_SCORING_SERVICES=
FLEETPULSE_LANE_STABILITY_EXCLUDED_SCORING_REF_PATTERNS=
```

### Workflow, Logging, and Alerts

```bash
FLEETPULSE_POWER_AUTOMATE_FLOW_URL=
FLEETPULSE_TEAMS_WEBHOOK_URL=
FLEETPULSE_CRITICAL_ALERT_SMS_TO=
FLEETPULSE_CENTRAL_LOG_URL=
FLEETPULSE_CENTRAL_LOG_API_KEY=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
```

### Power BI Publishing

```bash
FleetPulseBaseUrl=https://k1-fleetpulse.azurewebsites.net
POWERBI_WORKSPACE_ID=
POWERBI_WORKSPACE_NAME=
POWERBI_DATASET_NAME=
POWERBI_DASHBOARD_NAME=
POWERBI_NATIVE_REPORT_NAME=
POWERBI_ACCESS_TOKEN=
```

## Acceptance Gates

| Gate | Owner | Pass condition |
| --- | --- | --- |
| Source authority | Systems architecture | Every KPI has exactly one authoritative source and optional reference systems |
| Fleet certification | Fleet Ops Manager | Geotab row counts reconcile; safety, vehicle, location, and overview tables are non-empty |
| Track & Trace certification | Track & Trace lead | XTRA recency and trailer GPS merge are healthy; custody is labeled inferred unless Xcelerator confirms |
| Dispatch certification | Dispatch manager | Xcelerator event feed, route SLA, approval flow, and ownership state are healthy |
| Sales certification | Sales manager | Lane-stability endpoints return JSON and revenue reconciles to Xcelerator |
| Audit certification | Systems/BI | Logs, failures, duplicate suppressions, approvals, and alerts are queryable |
| Publish approval | Lead Systems Architect | No awaiting-feed KPI is presented as green |

## Risks and Controls

| Risk | Control |
| --- | --- |
| Dashboard shows false green when a feed is down | Display feed status and block certification for awaiting-feed metrics |
| GPS inference is mistaken for dispatch truth | Label custody as inferred and reconcile against Xcelerator assignment |
| Duplicate XTRA emails create duplicate trailer events | Use idempotency keys and test duplicate suppression before publish |
| Power BI endpoint falls through to frontend HTML | Validate content type/JSON shape, not just HTTP 200 |
| Revenue differs from Xcelerator | Reconcile company revenue to Xcelerator footer total before Sales publish |
| Human-agent ambiguity in dispatch queue | Require owner, claim, recommender, approver, timestamp, and approval reference |
| Secrets leak into dashboards or logs | Use GitHub Secrets or Key Vault and redact secrets in structured logs |

## Business Impact

- Fleet Ops Manager gets a verified live view of vehicle utilization, safety exposure, and terminal coverage.
- Track & Trace can locate trailers and vehicles faster while clearly separating inferred custody from dispatch truth.
- Dispatch gains exception ownership and approval traceability before automated actions affect operations.
- Sales gets lane and revenue stability KPIs only after Xcelerator reconciliation, avoiding bad pricing or service decisions from stale data.
- Systems gains a repeatable publish gate that scales across future Power BI pages without weakening source-of-truth governance.
