"""Safety scoring service — per-vehicle scores, trends, risk ranking."""

from __future__ import annotations

import random
import os
import threading
import time
from copy import deepcopy
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from geotab_client import GeotabClient
from models import SafetyBreakdown, TrendDirection, VehicleSafetyScore
from services.fleet_service import get_scoped_device_map

logger = logging.getLogger(__name__)


# K1 speeding policy: counts after 6 mph over posted speed limit
SPEEDING_THRESHOLD_MPH = 6
# Exception rule keywords → category mapping (Geotab built-in rule names)
_CATEGORY_KEYWORDS = {
    "speeding": ["speed", "posted"],
    "harsh_braking": ["hard brake", "harsh brake", "deceleration"],
    "harsh_acceleration": ["harsh accel", "hard accel", "acceleration"],
    "harsh_cornering": ["corner", "turning"],
}
_SAFETY_CACHE: dict[str, tuple[float, list[VehicleSafetyScore]]] = {}
_SAFETY_LOCKS: dict[str, threading.Lock] = {}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _cache_ttl_seconds() -> int:
    return max(0, _int_env("FLEETPULSE_CACHE_TTL_SECONDS", 30))


def _cache_fallback_seconds() -> int:
    return max(_cache_ttl_seconds(), _int_env("FLEETPULSE_CACHE_FALLBACK_SECONDS", 300))


def _cache_get(key: str, max_age_seconds: int) -> list[VehicleSafetyScore] | None:
    if max_age_seconds <= 0:
        return None
    entry = _SAFETY_CACHE.get(key)
    if not entry:
        return None
    created_at, scores = entry
    if time.time() - created_at > max_age_seconds:
        return None
    return deepcopy(scores)


def _cache_set(key: str, scores: list[VehicleSafetyScore]) -> None:
    _SAFETY_CACHE[key] = (time.time(), deepcopy(scores))


def _acquire_cache_lock(key: str) -> threading.Lock | None:
    lock = _SAFETY_LOCKS.setdefault(key, threading.Lock())
    return lock if lock.acquire(blocking=False) else None


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
        cache_key = f"safety:{days}"
        cached = _cache_get(cache_key, _cache_ttl_seconds())
        if cached is not None:
            return cached

        lock = _acquire_cache_lock(cache_key)
        if lock is None:
            fallback = _cache_get(cache_key, _cache_fallback_seconds())
            return fallback if fallback is not None else []

        try:
            cached = _cache_get(cache_key, _cache_ttl_seconds())
            if cached is not None:
                return cached
            scores = _get_geotab_safety_scores(days)
            _cache_set(cache_key, scores)
            return scores
        except TimeoutError as exc:
            logger.warning("safety_scores_unavailable_geotab_timeout", extra={"error": str(exc)})
            fallback = _cache_get(cache_key, _cache_fallback_seconds())
            return fallback if fallback is not None else []
        except Exception as exc:
            logger.warning("safety_scores_unavailable", extra={"error": str(exc)})
            return []
        finally:
            lock.release()
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
    device_map = get_scoped_device_map(client.get_devices())

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
    device_map = get_scoped_device_map(client.get_devices())

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
