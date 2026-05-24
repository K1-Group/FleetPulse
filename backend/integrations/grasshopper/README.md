# Grasshopper integration (placeholder)

No client module currently exists. The People & Systems and HR Call Analysis
dashboards currently consume Grasshopper-derived data via Power BI / Fabric
(see `integrations.powerbi`, `integrations.fabric_warehouse`).

When direct Grasshopper API access is added, drop the client here as
`client.py` and re-export through `__init__.py`.
