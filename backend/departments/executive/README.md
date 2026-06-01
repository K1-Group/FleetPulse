# Executive Department

Powers the Executive Command Seat dashboard. The executive view aggregates
fleet-wide KPIs and AI insights — it does not own source-system access.

## Composition (facade re-exports)

Routers (mounted in `backend/app.py`):
- `routers.dashboard` — `/api/dashboard`
- `routers.alerts` — `/api/alerts`
- `routers.gamification` — `/api/gamification`
- `routers.ai_chat` — `/api/ai`
- `routers.monitor` — `/api/monitor`

Services:
- `services.fleet_service`
- `services.alert_service`
- `services.gamification_service`
- `services.monitor_service`
- `services.dashboard_validation_service`

Source integrations (centralized — DO NOT duplicate here):
- `backend/integrations/xcelerator`
- `backend/integrations/powerbi`
- `backend/integrations/fabric_warehouse`

## Frontend counterpart

`frontend/src/departments/executive/`
