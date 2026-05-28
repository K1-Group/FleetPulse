"""Executive department service facade.

Re-exports the existing service modules used by the Executive Command Seat.
"""

from services import (
    alert_service,
    dashboard_validation_service,
    fleet_service,
    gamification_service,
    monitor_service,
)

__all__ = [
    "alert_service",
    "dashboard_validation_service",
    "fleet_service",
    "gamification_service",
    "monitor_service",
]
