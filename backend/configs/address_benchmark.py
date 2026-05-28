"""Runtime configuration for pickup/delivery address benchmarks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(int(os.getenv(name, str(default))), minimum)
    except ValueError:
        return default


def _env_float_optional(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return max(float(raw), 0.0)
    except ValueError:
        return None


@dataclass(frozen=True)
class AddressBenchmarkConfig:
    period_days: int = 180
    stop_threshold_minutes: int = 60
    minimum_history_samples: int = 2
    max_pairs: int = 50
    max_recent_orders_per_pair: int = 5
    max_source_rows: int = 5000
    timezone: str = "America/Chicago"
    xcelerator_source: str = "auto"
    evidence_path: str = ""
    cost_per_truck_hour: float | None = None

    @classmethod
    def from_env(cls) -> "AddressBenchmarkConfig":
        return cls(
            period_days=_env_int("FLEETPULSE_ADDRESS_BENCHMARK_PERIOD_DAYS", 180, 1),
            stop_threshold_minutes=_env_int(
                "FLEETPULSE_ADDRESS_BENCHMARK_STOP_THRESHOLD_MINUTES",
                60,
                1,
            ),
            minimum_history_samples=_env_int(
                "FLEETPULSE_ADDRESS_BENCHMARK_MIN_HISTORY_SAMPLES",
                2,
                1,
            ),
            max_pairs=_env_int("FLEETPULSE_ADDRESS_BENCHMARK_MAX_PAIRS", 50, 1),
            max_recent_orders_per_pair=_env_int(
                "FLEETPULSE_ADDRESS_BENCHMARK_MAX_RECENT_ORDERS_PER_PAIR",
                5,
                0,
            ),
            max_source_rows=_env_int(
                "FLEETPULSE_ADDRESS_BENCHMARK_MAX_SOURCE_ROWS",
                5000,
                1,
            ),
            timezone=os.getenv(
                "FLEETPULSE_ADDRESS_BENCHMARK_TIMEZONE",
                "America/Chicago",
            ).strip()
            or "America/Chicago",
            xcelerator_source=(
                os.getenv("FLEETPULSE_ADDRESS_BENCHMARK_XCELERATOR_SOURCE", "auto")
                .strip()
                .casefold()
                or "auto"
            ),
            evidence_path=os.getenv("FLEETPULSE_ADDRESS_BENCHMARK_EVIDENCE_PATH", "").strip(),
            cost_per_truck_hour=_env_float_optional(
                "FLEETPULSE_ADDRESS_BENCHMARK_COST_PER_TRUCK_HOUR"
            ),
        )

    def as_dict(self) -> dict[str, int | float | str | None]:
        return asdict(self)
