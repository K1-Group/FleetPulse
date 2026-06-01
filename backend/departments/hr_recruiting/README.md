# HR Recruiting Department

Powers the recruiting worklist and Power BI-bound HR recruiting view.

## Composition (facade re-exports)

Routers:
- `routers.hr_recruiting` — `/api/hr-recruiting`
- `routers.hr_recruiting_powerbi` — `/api/powerbi`

Services:
- `services.hr_recruiting_service`

Source integrations (centralized — DO NOT duplicate here):
- `backend/integrations/powerbi`
- `backend/integrations/sharepoint`
- `backend/integrations/outlook`

## Frontend counterpart

`frontend/src/departments/hr_recruiting/`
