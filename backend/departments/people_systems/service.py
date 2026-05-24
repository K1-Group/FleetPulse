"""People & Systems department service facade."""

from services import (
    auth_session_service,
    entra_seat_access_service,
    hr_call_analysis_service,
    seat_kpi_feed_service,
)

__all__ = [
    "auth_session_service",
    "entra_seat_access_service",
    "hr_call_analysis_service",
    "seat_kpi_feed_service",
]
