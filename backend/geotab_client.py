"""Geotab API wrapper with auth caching and re-auth on expiry."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import concurrent.futures
import logging

import mygeotab
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


# Thread pool for timeout-wrapping blocking Geotab calls. Keep this bounded so
# slow upstream calls cannot consume unbounded App Service threads.
_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=max(1, _int_env("FLEETPULSE_GEOTAB_MAX_WORKERS", 4))
)

# Try loading creds from the openclaw env file, fall back to project .env
_env_geotab = Path.home() / ".openclaw" / ".env.geotab"
if _env_geotab.exists():
    load_dotenv(_env_geotab)
else:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class GeotabClient:
    """Thin wrapper around the mygeotab SDK with credential caching."""

    _instance: GeotabClient | None = None

    def __init__(self):
        self.username = os.getenv("GEOTAB_USERNAME", "")
        self.password = os.getenv("GEOTAB_PASSWORD", "")
        self.database = os.getenv("GEOTAB_DATABASE", "k1logistics")
        self.server = os.getenv("GEOTAB_SERVER", "my.geotab.com")
        self._api: mygeotab.API | None = None
        self._auth_time: float = 0

    # ── singleton ─────────────────────────────────────────────
    @classmethod
    def get(cls) -> "GeotabClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── auth ─────────────────────────────────────────────────
    def _needs_auth(self) -> bool:
        return self._api is None or (time.time() - self._auth_time > 3600)

    def authenticate(self) -> mygeotab.API:
        if not self._needs_auth():
            return self._api  # type: ignore
        self._api = mygeotab.API(
            username=self.username,
            password=self.password,
            database=self.database,
            server=self.server,
        )
        self._api.authenticate()
        self._auth_time = time.time()
        return self._api

    @property
    def api(self) -> mygeotab.API:
        return self.authenticate()

    # ── timeout helper ─────────────────────────────────────────
    def _call(self, fn, *args, timeout: float | None = None, **kwargs):
        """Run a blocking Geotab call with a timeout (default 5s)."""
        timeout = timeout or _float_env("FLEETPULSE_GEOTAB_TIMEOUT_SECONDS", 10.0)
        future = _executor.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            logger.warning(f"Geotab API call timed out after {timeout}s: {fn.__name__ if hasattr(fn, '__name__') else fn}")
            raise TimeoutError(f"Geotab API call timed out after {timeout}s")

    # ── data methods ───────────────────────────────────────────
    def get_devices(self) -> list[dict[str, Any]]:
        return self._call(self.api.get, "Device")

    def get_trips(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        to_date = to_date or datetime.now(timezone.utc)
        from_date = from_date or (to_date - timedelta(days=1))
        search = {
            "fromDate": from_date.isoformat(),
            "toDate": to_date.isoformat(),
        }
        return self._call(
            self.api.get,
            "Trip",
            search=search,
        )

    def get_exception_events(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        to_date = to_date or datetime.now(timezone.utc)
        from_date = from_date or (to_date - timedelta(days=7))
        return self._call(
            self.api.get,
            "ExceptionEvent",
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
        )

    def get_status_data(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        diagnostic_id: str | None = None,
    ) -> list[dict[str, Any]]:
        to_date = to_date or datetime.now(timezone.utc)
        from_date = from_date or (to_date - timedelta(hours=4))
        search: dict[str, Any] = {
            "fromDate": from_date.isoformat(),
            "toDate": to_date.isoformat(),
        }
        if diagnostic_id:
            search["diagnosticSearch"] = {"id": diagnostic_id}
        return self._call(self.api.get, "StatusData", search=search)

    def get_zones(self) -> list[dict[str, Any]]:
        return self._call(self.api.get, "Zone")

    def get_groups(self) -> list[dict[str, Any]]:
        return self._call(self.api.get, "Group")

    def get_device_status_info(self) -> list[dict[str, Any]]:
        """DeviceStatusInfo gives current lat/lon, speed, bearing, etc."""
        return self._call(self.api.get, "DeviceStatusInfo")

    def add_zone(self, zone_data: dict[str, Any]) -> str:
        return self._call(self.api.add, "Zone", zone_data)
