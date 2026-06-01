"""Dashboard date-range helpers for server-side aggregation filters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class DashboardDateRange:
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def contains_date(self, value: date | None) -> bool:
        return bool(value and self.start <= value <= self.end)

    def contains_datetime(self, value: datetime | None) -> bool:
        return self.contains_date(value.date() if value else None)

    def previous(self) -> "DashboardDateRange":
        previous_end = self.start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=self.days - 1)
        return DashboardDateRange(start=previous_start, end=previous_end)

    def as_dict(self) -> dict[str, Any]:
        previous = self.previous()
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "days": self.days,
            "previous_start": previous.start.isoformat(),
            "previous_end": previous.end.isoformat(),
        }


def dashboard_date_range(
    start_date: date | str | None,
    end_date: date | str | None,
) -> DashboardDateRange | None:
    """Return an inclusive range when at least one bound is provided."""

    start = _coerce_date(start_date)
    end = _coerce_date(end_date)
    if not start and not end:
        return None
    if start and not end:
        end = start
    if end and not start:
        start = end
    assert start is not None and end is not None
    if start > end:
        start, end = end, start
    return DashboardDateRange(start=start, end=end)


def pct_change(current: int | float, previous: int | float) -> float | None:
    if previous == 0:
        return None if current == 0 else 100.0
    return round(((current - previous) / previous) * 100, 1)


def _coerce_date(value: date | str | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
