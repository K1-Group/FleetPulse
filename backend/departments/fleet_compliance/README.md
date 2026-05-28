# Fleet & Compliance Department

Powers the Fleet & Compliance Manager Seat dashboard: maintenance, coaching,
geofences, fuel ops, ELD compliance, vehicle inventory, safety scoring, data
connector.

## Composition (facade re-exports)

Routers:
- `routers.maintenance` — `/api/maintenance`
- `routers.coaching` — `/api/coaching`
- `routers.geofences` — `/api/geofences`
- `routers.fuel` — `/api/fuel`
- `routers.compliance` — `/api/compliance`
- `routers.vehicles` — `/api/vehicles`
- `routers.safety` — `/api/safety`
- `routers.data_connector` — `/api/data-connector`

Services:
- `services.coaching_service`
- `services.safety_service`
- `services.alert_service` (vehicle/safety alerts)
- `services.fleet_service` (vehicle inventory)

Source integrations (centralized — DO NOT duplicate here):
- `backend/integrations/geotab`
- `backend/integrations/atob_fuel`

## Frontend counterpart

`frontend/src/departments/fleet_compliance/`
