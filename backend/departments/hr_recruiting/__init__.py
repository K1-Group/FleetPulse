"""HR Recruiting department facade.

Distinct from People & Systems: this folder owns the recruiting worklist and
Power BI report bindings specific to hiring. Call analytics that span all
departments live under `departments.people_systems`.
"""

from . import contracts, router, service  # noqa: F401
