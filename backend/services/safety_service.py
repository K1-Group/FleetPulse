"""Safety scoring service — per-vehicle scores, trends, risk ranking."""

from __future__ import annotations

import random
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from geotab_client import GeotabClient
from models import SafetyBreakdown, TrendDirection, VehicleSafetyScore


# K1 speeding policy: counts after 6 mph over posted speed limit
SPEEDING_THRESHOLD_MPH = 6
# Exception rule keywords → category mapping (Geotab built-in rule names)
_CATEGORY_KEYWORDS = {
    "speeding": ["speed", "posted"],
    "harsh_braking": ["hard brake", "harsh brake", "deceleration"],
    "harsh_acceleration": ["harsh accel", "hard accel", "acceleration"],
    "harsh_cornering": ["corner", "turning"],
}


def _categorize_event(rule_name: str) -> str | None:
    lower = rule_name.lower()
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return cat
    return None


def _compute_score(breakdown: SafetyBreakdown) -> float:
    """Score 0-100: starts at 100, deducts for each incident type."""
    total = (
        breakdown.speeding * 3
        + breakdown.harsh_braking * 4
        + breakdown.harsh_acceleration * 2
        + breakdown.harsh_cornering * 2
    )
    return max(0.0, round(100 - total, 1))


def get_safety_scores(days: int = 7) -> list[VehicleSafetyScore]:
    """Get safety scores from real Geotab ExceptionEvents."""
    if not _use_demo_safety_scores():
        return _get_geotab_safety_scores(days)
    return _get_demo_safety_scores()


def _use_demo_safety_scores() -> bool:
    return os.getenv("FLEETPULSE_SAFETY_DEMO_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _get_demo_safety_scores() -> list[VehicleSafetyScore]:
    """Return deterministic demo scores only when explicitly enabled."""
    client = GeotabClient.get()
    devices = client.get_devices()
    device_map = {d["id"]: d.get("name", "Unknown") for d in devices}

    results: list[VehicleSafetyScore] = []
    random.seed(42)

    for idx, (vid, name) in enumerate(device_map.items()):
        if idx % 3 == 0:
            speeding = random.randint(2, 6)
            harsh_braking = random.randint(1, 3)
            harsh_acceleration = random.randint(1, 4)
            harsh_cornering = random.randint(0, 2)
        elif idx % 3 == 1:
            speeding = random.randint(0, 2)
            harsh_braking = random.randint(0, 2)
            harsh_acceleration = random.randint(0, 2)
            harsh_cornering = random.randint(0, 1)
        else:
            speeding = random.randint(0, 1)
            harsh_braking = 0
            harsh_acceleration = 0
            harsh_cornering = 0

        bd = SafetyBreakdown(
            speeding=speeding,
            harsh_braking=harsh_braking,
            harsh_acceleration=harsh_acceleration,
            harsh_cornering=harsh_cornering,
        )
        score = _compute_score(bd)
        trend_choice = random.choice([TrendDirection.IMPROVING, TrendDirection.STABLE, TrendDirection.DECLINING])
        total_events = bd.speeding + bd.harsh_braking + bd.harsh_acceleration + bd.harsh_cornering

        results.append(
            VehicleSafetyScore(
                vehicle_id=vid,
                vehicle_name=name,
                score=score,
                breakdown=bd,
                trend=trend_choice,
                event_count=total_events,
            )
        )

    results.sort(key=lambda x: x.score)
    return results


def _get_geotab_safety_scores(days: int) -> list[VehicleSafetyScore]:
    client = GeotabClient.get()
    devices = client.get_devices()
    device_map = {d["id"]: d.get("name", "Unknown") for d in devices}

    now = datetime.now(timezone.utc)
    events = client.get_exception_events(now - timedelta(days=days), now)
    prior_events = client.get_exception_events(now - timedelta(days=days * 2), now - timedelta(days=days))

    current = _build_breakdown(events)
    prior = _build_breakdown(prior_events)

    results: list[VehicleSafetyScore] = []
    for vid, name in device_map.items():
        bd = current.get(vid, SafetyBreakdown())
        score_now = _compute_score(bd)
        bd_prior = prior.get(vid, SafetyBreakdown())
        score_prior = _compute_score(bd_prior)

        if score_now > score_prior + 3:
            trend = TrendDirection.IMPROVING
        elif score_now < score_prior - 3:
            trend = TrendDirection.DECLINING
        else:
            trend = TrendDirection.STABLE

        total_events = bd.speeding + bd.harsh_braking + bd.harsh_acceleration + bd.harsh_cornering
        results.append(
            VehicleSafetyScore(
                vehicle_id=vid,
                vehicle_name=name,
                score=score_now,
                breakdown=bd,
                trend=trend,
                event_count=total_events,
            )
        )

    results.sort(key=lambda x: x.score)
    return results


def _build_breakdown(evts: list[dict[str, Any]]) -> dict[str, SafetyBreakdown]:
    per_vehicle: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for event in evts:
        dev_id = event.get("device", {}).get("id")
        rule_name = event.get("rule", {}).get("name", "")
        category = _categorize_event(rule_name)
        if dev_id and category:
            per_vehicle[dev_id][category] += 1
    return {vid: SafetyBreakdown(**counts) for vid, counts in per_vehicle.items()}
