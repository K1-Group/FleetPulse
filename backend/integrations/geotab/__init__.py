"""Geotab source-system integration.

Wraps the existing top-level `geotab_client` module. All Geotab API access
should go through this package so department dashboards never instantiate
Geotab clients directly.
"""

from geotab_client import *  # noqa: F401,F403
import geotab_client as client  # noqa: F401

__all__ = ["client"]
