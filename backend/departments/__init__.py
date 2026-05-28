"""FleetPulse department-oriented packages.

Each subpackage groups the existing routers, services, and contracts that serve
a specific department's dashboard. Modules under this package are facades that
re-export from `backend/routers/*` and `backend/services/*` so that current
application paths and imports remain functional during the restructure.

Source-system integrations (Xcelerator, Geotab, QBO, AtoB Fuel, SharePoint,
Outlook, Grasshopper) must stay centralized under `backend/integrations/` and
are not copied into department folders.
"""
