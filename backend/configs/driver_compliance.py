"""Runtime configuration for Driver Compliance document projections."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(int(os.getenv(name, str(default))), minimum)
    except ValueError:
        return default


@dataclass(frozen=True)
class DriverComplianceConfig:
    source: str = "pending_register"
    source_path: str = ""
    source_url: str = ""
    warning_days: int = 45
    stale_minutes: int = 1440
    timeout_seconds: int = 20
    timezone: str = "America/Chicago"

    @classmethod
    def from_env(cls) -> "DriverComplianceConfig":
        return cls(
            source=os.getenv("FLEETPULSE_DRIVER_COMPLIANCE_SOURCE", "pending_register").strip().casefold()
            or "pending_register",
            source_path=os.getenv("FLEETPULSE_DRIVER_COMPLIANCE_SOURCE_PATH", "").strip(),
            source_url=os.getenv("FLEETPULSE_DRIVER_COMPLIANCE_SOURCE_URL", "").strip(),
            warning_days=_env_int("FLEETPULSE_DRIVER_COMPLIANCE_WARNING_DAYS", 45, 1),
            stale_minutes=_env_int("FLEETPULSE_DRIVER_COMPLIANCE_STALE_MINUTES", 1440, 1),
            timeout_seconds=_env_int("FLEETPULSE_DRIVER_COMPLIANCE_TIMEOUT_SECONDS", 20, 1),
            timezone=os.getenv("FLEETPULSE_DRIVER_COMPLIANCE_TIMEZONE", "America/Chicago").strip()
            or "America/Chicago",
        )

    def as_dict(self) -> dict[str, int | str]:
        return asdict(self)
