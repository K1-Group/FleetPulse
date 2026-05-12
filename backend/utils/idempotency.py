"""Stable idempotency key helpers."""

from __future__ import annotations

import hashlib


def stable_idempotency_key(namespace: str, *parts: object) -> str:
    """Return a deterministic key for source events and side effects."""

    canonical = "|".join(str(part or "").strip() for part in parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"
