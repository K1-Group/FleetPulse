# Operations Department

Powers the Operations Manager Seat dashboard: control tower, K1 operating
system, trip/route replay, fleet reports, lane stability.

## Composition (facade re-exports)

Routers:
- `routers.control_tower` — `/api/control-tower`
- `routers.operating_system` — `/api/operating-system`
- `routers.trips` — `/api/trips`
- `routers.reports` — `/api/reports`
- `routers.lane_stability` — `/api/lane-stability`

Services:
- `services.control_tower_service`
- `services.control_tower_seat_kpi_service`
- `services.operating_system_service`
- `services.k1l_operating_kpi_service`
- `services.k1l_weekly_engine_kpi_service`
- `services.delivery_center_performance_service`
- `services.lane_stability_service`
- `services.lakehouse_lane_stability_service`
- `services.fleet_report_delivery_service`
- `services.trailer_tracking_service`
- `services.xtra_lease_ingestion_service`
- `services.scheduled_feed_contract_service`

Source integrations (centralized — DO NOT duplicate here):
- `backend/integrations/xcelerator`
- `backend/integrations/geotab`
- `backend/integrations/fabric_warehouse`
- `backend/integrations/sharepoint`

## Frontend counterpart

`frontend/src/departments/operations/`
