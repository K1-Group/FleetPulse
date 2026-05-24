# Revenue Department

Powers the Revenue Manager Seat dashboard: driver workforce productivity,
revenue/cpm projections, lane stability rollup.

## Composition (facade re-exports)

Routers:
- `routers.driver_workforce` — `/api/driver-workforce`
- `routers.lane_stability` — `/api/lane-stability` (shared, revenue rollup)

Services:
- `services.driver_workforce_service`
- `services.revenue_productivity_service`
- `services.entity_margin_service` (shared with finance)
- `services.xcelerator_event_feed_service`
- `services.xcelerator_review_orders_import_service`

Source integrations (centralized — DO NOT duplicate here):
- `backend/integrations/xcelerator`
- `backend/integrations/fabric_warehouse`
- `backend/integrations/powerbi`

## Frontend counterpart

`frontend/src/departments/revenue/`
