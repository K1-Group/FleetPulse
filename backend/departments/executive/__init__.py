"""Executive department facade.

Re-exports the existing routers, services, and contracts that power the
Executive Command Seat dashboard. No behavior change vs `backend/routers/*`
and `backend/services/*`.
"""

from . import contracts, router, service  # noqa: F401
