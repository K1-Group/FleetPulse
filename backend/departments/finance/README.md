# Finance Department

Powers the Finance Controller Seat dashboard: operating cost, QBO-sourced
financials, margin/cpm projections, fuel cost roll-ups.

## Composition (facade re-exports)

Routers:
- `routers.fuel` — `/api/fuel` (shared with fleet_compliance; financial roll-up here)

Services:
- `services.operating_cost_service`
- `services.qbo_financial_feed_import_service`
- `services.qbo_financial_snapshot_service`
- `services.qbo_expense_import_service`
- `services.atob_fuel_expense_service`
- `services.entity_margin_service`

Source integrations (centralized — DO NOT duplicate here):
- `backend/integrations/qbo`
- `backend/integrations/atob_fuel`
- `backend/integrations/powerbi` (Xcelerator CEO model for CPM)

## Frontend counterpart

`frontend/src/departments/finance/`
