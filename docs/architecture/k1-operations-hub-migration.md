# K1 Operations Hub Migration

## Decision

FleetPulse will replace the legacy K1 Command Center front-end over time. The
replacement is presentation-layer only. Backend services stay separate and keep
their existing source-of-truth boundaries.

## Boundaries

FleetPulse owns:

- Read-only operating dashboard shell
- Fleet, fuel, maintenance, safety, and exception visibility
- Read-only projections from Geotab, Xcelerator, AP Agent, FinanceOps, Power BI,
  SharePoint, and QBO status services
- Cross-system status cards, health indicators, and drill-through links

FleetPulse does not own:

- QBO bill creation, approval, or payment export logic
- AP Agent retry/recovery rules
- FinanceOps transaction lineage or reconciliation ledger
- Xcelerator dispatch, revenue, pay, contract, or load lifecycle state
- Geotab telemetry, maintenance, safety, or vehicle source records
- Secrets, webhook URLs, or OAuth refresh-token storage

## Service Separation

| Domain | Front-end Surface | Backend Owner | Source Of Truth | Write Policy |
| --- | --- | --- | --- | --- |
| Fleet telemetry | FleetPulse dashboard | FleetPulse services | Geotab | Read-only |
| Dispatch/load state | FleetPulse reference cards | Xcelerator adapter | Xcelerator | Read-only reference |
| AP lifecycle | FleetPulse AP status card | AP Agent Foundry/API | AP Agent + QBO + SharePoint | No direct FleetPulse write |
| QBO bill creation | Status only | AP/QBO function or Zapier bridge | QBO | External approved flow only |
| Finance reconciliation | Health/status cards only | financeops-command-center | SharePoint ledger + Power BI | Read-only pilot |
| Executive BI | Embedded/link cards | Power BI/Fabric | Power BI semantic models | Read-only |

## Replacement Phases

1. Inventory every legacy K1 Command Center page, card, and API dependency.
2. Map each surface to a FleetPulse tab or card without moving backend logic.
3. Add FleetPulse read-only adapters for AP lifecycle and FinanceOps health.
4. Run K1 Command Center and FleetPulse side-by-side for parity checks.
5. Retire legacy UI routes only after the FleetPulse card has matching data,
   source labels, and stale-feed indicators.

## Production Gates

- No FleetPulse route may mutate Xcelerator, Geotab, QBO, FinanceOps, or AP
  Agent state.
- Every cross-system card must show source authority and feed health.
- Missing feeds must render `awaiting_feed` or `unavailable`; never fill with
  fake operating values.
- FinanceOps remains a separate repo and service until read-only reconciliation
  has stable production history.
- `FLEETPULSE_ENABLE_WRITEBACK` must remain unset or `false`.

## Required Config

```bash
FLEETPULSE_ENABLE_AP_STATUS=true
FLEETPULSE_AP_LIFECYCLE_API_URL=<ap-lifecycle-endpoint>
FLEETPULSE_FINANCEOPS_HEALTH_API_URL=<financeops-health-endpoint>
FLEETPULSE_POWERBI_WORKSPACE_ID=<workspace-id>
FLEETPULSE_ENABLE_WRITEBACK=false
```

## Rollback

If a FleetPulse replacement card is incomplete, keep the K1 Command Center route
available and mark the FleetPulse card as `awaiting_feed`. Rollback is UI-only:
disable the card or tab without changing backend services.
