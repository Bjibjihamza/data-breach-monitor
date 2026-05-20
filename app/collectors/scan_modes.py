"""Shared constants and helpers for collector scan modes.

The project exposes two scan modes:

- ``backfill``      one-shot historical sweep with a strict global ceiling.
                    Used automatically on first Docker startup so the system
                    has data without scanning forever.
- ``incremental``   default mode for dashboard/manual/scheduled scans.
                    Skips items already present in Elasticsearch and stops
                    when known items dominate the result set.

A small helper :func:`normalize_scan_mode` is provided so collectors and
API endpoints accept the mode in a forgiving way (``"BACKFILL"``,
``" incremental "``, ``None`` etc.) without coupling on the exact string.
"""

from __future__ import annotations

import logging
from typing import Literal


logger = logging.getLogger(__name__)

SCAN_MODE_BACKFILL = "backfill"
SCAN_MODE_INCREMENTAL = "incremental"
DEFAULT_SCAN_MODE = SCAN_MODE_INCREMENTAL
ALLOWED_SCAN_MODES: frozenset[str] = frozenset({SCAN_MODE_BACKFILL, SCAN_MODE_INCREMENTAL})

ScanMode = Literal["backfill", "incremental"]

INITIAL_BACKFILL_STATE_KEY = "initial_backfill_completed"
LAST_RUN_STATE_KEY = "last_run"
COLLECTOR_STATE_KEY = "collector"


def normalize_scan_mode(value: str | None, *, default: str = DEFAULT_SCAN_MODE) -> str:
    """Return one of ``backfill``/``incremental``; falls back to ``default``."""

    if value is None:
        return default
    candidate = str(value).strip().lower()
    if candidate in ALLOWED_SCAN_MODES:
        return candidate
    if candidate:
        logger.warning("Ignoring unknown scan mode %r; using %s.", value, default)
    return default


def is_backfill(mode: str | None) -> bool:
    return normalize_scan_mode(mode) == SCAN_MODE_BACKFILL


def is_incremental(mode: str | None) -> bool:
    return normalize_scan_mode(mode) == SCAN_MODE_INCREMENTAL
