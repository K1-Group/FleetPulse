"""Runtime configuration for Driver Workforce route-window projections."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(int(os.getenv(name, str(default))), minimum)
    except ValueError:
        return default


@dataclass(frozen=True)
class DriverWorkforceConfig:
    late_start_grace_minutes: int = 15
    near_limit_minutes: int = 60
    recent_driving_activity_minutes: int = 30
    recent_work_contact_minutes: int = 120
    actual_start_lookback_minutes: int = 60
    completion_tolerance_minutes: int = 10
    source_stale_minutes: int = 180
    timezone: str = "America/Chicago"
    xcelerator_source: str = "ceo_powerbi"
    ceo_powerbi_fallback_source: str = "fabric_warehouse_sql"

    @classmethod
    def from_env(cls) -> "DriverWorkforceConfig":
        return cls(
            late_start_grace_minutes=_env_int(
                "FLEETPULSE_DRIVER_WORKFORCE_LATE_START_GRACE_MINUTES", 15, 1
            ),
            near_limit_minutes=_env_int(
                "FLEETPULSE_DRIVER_WORKFORCE_NEAR_LIMIT_MINUTES", 60, 1
            ),
            recent_driving_activity_minutes=_env_int(
                "FLEETPULSE_DRIVER_WORKFORCE_RECENT_DRIVING_ACTIVITY_MINUTES", 30, 1
            ),
            recent_work_contact_minutes=_env_int(
                "FLEETPULSE_DRIVER_WORKFORCE_RECENT_WORK_CONTACT_MINUTES", 120, 1
            ),
            actual_start_lookback_minutes=_env_int(
                "FLEETPULSE_DRIVER_WORKFORCE_ACTUAL_START_LOOKBACK_MINUTES", 60, 0
            ),
            completion_tolerance_minutes=_env_int(
                "FLEETPULSE_DRIVER_WORKFORCE_COMPLETION_TOLERANCE_MINUTES", 10, 0
            ),
            source_stale_minutes=_env_int(
                "FLEETPULSE_DRIVER_WORKFORCE_SOURCE_STALE_MINUTES", 180, 1
            ),
            timezone=os.getenv(
                "FLEETPULSE_DRIVER_WORKFORCE_TIMEZONE", "America/Chicago"
            ).strip()
            or "America/Chicago",
            xcelerator_source=(
                os.getenv("FLEETPULSE_DRIVER_WORKFORCE_XCELERATOR_SOURCE", "ceo_powerbi")
                .strip()
                .casefold()
                or "ceo_powerbi"
            ),
            ceo_powerbi_fallback_source=(
                os.getenv("FLEETPULSE_DRIVER_WORKFORCE_CEO_POWERBI_FALLBACK", "fabric_warehouse_sql")
                .strip()
                .casefold()
                or "fabric_warehouse_sql"
            ),
        )

    def as_dict(self) -> dict[str, int | str]:
        return asdict(self)
