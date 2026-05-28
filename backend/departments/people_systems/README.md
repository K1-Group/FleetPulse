# People & Systems Department

Powers the People & Systems Manager Seat dashboard: department call analysis,
HR call analysis, organizational KPI rollups.

`hr_recruiting` lives in its own department folder so the recruiting worklist
and Grasshopper-driven call analytics remain separable from the broader People
& Systems org view.

## Composition (facade re-exports)

Routers:
- `routers.department_call_analysis` — `/api/department-call-analysis`
- `routers.hr_call_analysis` — `/api/hr-call-analysis`
- `routers.hr_call_analysis_powerbi` — `/api/powerbi`

Services:
- `services.hr_call_analysis_service`
- `services.seat_kpi_feed_service`
- `services.entra_seat_access_service`
- `services.auth_session_service`

Source integrations (centralized — DO NOT duplicate here):
- `backend/integrations/grasshopper` (call recordings, ingestion)
- `backend/integrations/powerbi`

## Frontend counterpart

`frontend/src/departments/people_systems/`
