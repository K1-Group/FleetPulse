"""Runtime configuration for Employee Workforce Time Doctor projections."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(int(os.getenv(name, str(default))), minimum)
    except ValueError:
        return default


@dataclass(frozen=True)
class EmployeeWorkforceConfig:
    source: str = "time_doctor"
    activity_feed_path: str = ""
    activity_feed_url: str = ""
    api_base_url: str = ""
    api_token_configured: bool = False
    company_id: str = ""
    lookback_days: int = 7
    stale_minutes: int = 180
    timeout_seconds: int = 20
    timezone: str = "America/Chicago"

    @classmethod
    def from_env(cls) -> "EmployeeWorkforceConfig":
        return cls(
            source=os.getenv("FLEETPULSE_EMPLOYEE_WORKFORCE_SOURCE", "time_doctor").strip().casefold()
            or "time_doctor",
            activity_feed_path=os.getenv("FLEETPULSE_TIMEDOCTOR_ACTIVITY_FEED_PATH", "").strip(),
            activity_feed_url=os.getenv("FLEETPULSE_TIMEDOCTOR_ACTIVITY_FEED_URL", "").strip(),
            api_base_url=os.getenv("FLEETPULSE_TIMEDOCTOR_API_BASE_URL", "").strip(),
            api_token_configured=bool(os.getenv("FLEETPULSE_TIMEDOCTOR_API_TOKEN", "").strip()),
            company_id=os.getenv("FLEETPULSE_TIMEDOCTOR_COMPANY_ID", "").strip(),
            lookback_days=_env_int("FLEETPULSE_EMPLOYEE_WORKFORCE_LOOKBACK_DAYS", 7, 1),
            stale_minutes=_env_int("FLEETPULSE_EMPLOYEE_WORKFORCE_STALE_MINUTES", 180, 1),
            timeout_seconds=_env_int("FLEETPULSE_TIMEDOCTOR_TIMEOUT_SECONDS", 20, 1),
            timezone=os.getenv("FLEETPULSE_EMPLOYEE_WORKFORCE_TIMEZONE", "America/Chicago").strip()
            or "America/Chicago",
        )

    def as_dict(self) -> dict[str, int | str | bool]:
        return asdict(self)
