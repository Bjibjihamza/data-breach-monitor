from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from redis import Redis

from app.config import settings


logger = logging.getLogger(__name__)

_KEY_PREFIX = "data_breach_monitor:scan_status:"
_TTL_SECONDS = 60 * 60 * 24 * 14


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client() -> Redis:
    return Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=0.25,
        socket_timeout=0.25,
    )


def _key(source: str) -> str:
    return f"{_KEY_PREFIX}{source}"


def _write(source: str, payload: dict[str, Any]) -> None:
    try:
        client = _client()
        client.setex(_key(source), _TTL_SECONDS, json.dumps(payload, default=str))
    except Exception as exc:
        logger.warning("Unable to persist scan status for %s: %s", source, exc.__class__.__name__)


def mark_scan_queued(source: str, *, task_id: str | None = None) -> None:
    started_at = _now()
    _write(
        source,
        {
            "source": source,
            "state": "queued",
            "status": "warning",
            "task_id": task_id or "",
            "last_scan_time": started_at,
            "started_at": started_at,
            "ended_at": "",
            "last_scan_result": "queued",
            "indexed_last_scan": 0,
            "duplicates_skipped": 0,
            "errors": 0,
        },
    )


def mark_scan_running(source: str) -> None:
    started_at = _now()
    existing = get_scan_status(source) or {}
    existing.update(
        {
            "source": source,
            "state": "running",
            "status": "warning",
            "last_scan_time": started_at,
            "started_at": started_at,
            "ended_at": "",
            "last_scan_result": "running",
        }
    )
    _write(source, existing)


def mark_scan_completed(source: str, result: dict[str, Any]) -> None:
    errors = int(result.get("errors") or 0)
    ended_at = str(result.get("ended_at") or _now())
    indexed = int(result.get("indexed") or result.get("saved") or 0)
    duplicates = int(result.get("duplicates_skipped") or 0)
    _write(
        source,
        {
            **result,
            "source": source,
            "state": "completed",
            "status": "warning" if errors else "healthy",
            "last_scan_time": ended_at,
            "started_at": str(result.get("started_at") or ""),
            "ended_at": ended_at,
            "last_scan_result": "completed_with_errors" if errors else "success",
            "indexed_last_scan": indexed,
            "duplicates_skipped": duplicates,
            "errors": errors,
        },
    )


def mark_scan_failed(source: str, error: str) -> None:
    ended_at = _now()
    _write(
        source,
        {
            "source": source,
            "state": "failed",
            "status": "error",
            "last_scan_time": ended_at,
            "started_at": "",
            "ended_at": ended_at,
            "last_scan_result": error or "failed",
            "indexed_last_scan": 0,
            "duplicates_skipped": 0,
            "errors": 1,
        },
    )


def get_scan_status(source: str) -> dict[str, Any] | None:
    redis_host = urlparse(settings.REDIS_URL).hostname or ""
    if redis_host not in {"", "localhost", "127.0.0.1"} and not Path("/.dockerenv").exists():
        logger.debug("Skipping scan status lookup for %s outside Docker host=%s.", source, redis_host)
        return None
    try:
        raw = _client().get(_key(source))
    except Exception as exc:
        logger.warning("Unable to read scan status for %s: %s", source, exc.__class__.__name__)
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def get_all_scan_statuses(sources: list[str]) -> dict[str, dict[str, Any]]:
    return {source: status for source in sources if (status := get_scan_status(source)) is not None}
