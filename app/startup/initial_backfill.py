"""Run-once initial backfill orchestration.

When the Docker stack is freshly built/started this module ensures that each
external collector performs a single bounded historical sweep so the system
has data without scanning forever. Subsequent restarts are no-ops because the
completion state is persisted in Elasticsearch
(``collection_state`` index, key ``initial_backfill_completed``).

The orchestration is deliberately tolerant of unavailable services:

- it waits for Elasticsearch to become reachable (with a bounded retry budget);
- if Celery is down it falls back to running the backfill inline (still bounded
  by ``INITIAL_BACKFILL_MAX_ITEMS_PER_SOURCE``);
- it never blocks the API forever - a single thread runs the orchestration in
  the background.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.collectors.scan_modes import COLLECTOR_STATE_KEY, INITIAL_BACKFILL_STATE_KEY, SCAN_MODE_BACKFILL
from app.config import settings
from app.storage.elastic_client import (
    ElasticsearchUnavailableError,
    get_collection_state,
    wait_for_elasticsearch,
)


logger = logging.getLogger(__name__)
_HUMAN_NAMES = {
    "github": "GitHub",
    "google_alerts": "Google Alerts",
    "telegram": "Telegram",
}
_lock = threading.Lock()
_started = False


def _is_completed(source: str) -> bool:
    try:
        collector_state = get_collection_state(source, COLLECTOR_STATE_KEY) or {}
        if collector_state.get("first_run_completed"):
            return True
        state = get_collection_state(source, INITIAL_BACKFILL_STATE_KEY) or {}
    except Exception as exc:
        logger.warning("Unable to read initial backfill state for %s: %s", source, exc.__class__.__name__)
        return False
    return bool(state.get("completed"))


def _source_enabled(source: str) -> bool:
    if source == "github":
        return bool(settings.GITHUB_TOKEN)
    if source == "google_alerts":
        return True
    if source == "telegram":
        return bool(settings.TELEGRAM_API_ID and settings.TELEGRAM_API_HASH)
    return False


def _human(source: str) -> str:
    return _HUMAN_NAMES.get(source, source)


def _enqueue_or_run_inline(source: str) -> dict[str, Any]:
    """Try to enqueue the backfill task via Celery; fall back to inline call."""

    from app.tasks import (  # local import: avoids circular import at module load
        run_google_alerts_scan,
        scan_github_task,
        scan_telegram_channels,
    )

    task_map = {
        "github": scan_github_task,
        "google_alerts": run_google_alerts_scan,
        "telegram": scan_telegram_channels,
    }
    task = task_map.get(source)
    if task is None:
        return {"status": "skipped", "reason": "unknown_source"}

    try:
        async_result = task.delay(mode=SCAN_MODE_BACKFILL)
        return {"status": "enqueued", "task_id": async_result.id}
    except Exception as exc:
        logger.warning(
            "Unable to enqueue %s initial backfill via Celery (%s); running inline.",
            source,
            exc.__class__.__name__,
        )
        try:
            result = task.run(mode=SCAN_MODE_BACKFILL)
        except Exception as inline_exc:
            logger.exception("Inline %s initial backfill failed: %s", source, inline_exc)
            return {"status": "error", "error": inline_exc.__class__.__name__}
        return {
            "status": "completed",
            "collected": int(result.get("collected") or result.get("messages_collected") or 0),
            "indexed": int(result.get("indexed") or result.get("saved") or 0),
            "skipped_existing": int(result.get("skipped_existing") or 0),
            "errors": int(result.get("errors") or 0),
        }


def _orchestrate() -> dict[str, dict[str, Any]]:
    logger.info("Initial backfill check started")
    summary: dict[str, dict[str, Any]] = {}

    try:
        wait_for_elasticsearch()
    except ElasticsearchUnavailableError:
        logger.error("Initial backfill aborted: Elasticsearch not reachable.")
        return {source: {"status": "skipped", "reason": "elasticsearch_unavailable"} for source in _HUMAN_NAMES}

    for source in ("github", "google_alerts", "telegram"):
        if not _source_enabled(source):
            logger.info("Skipping %s initial backfill: source is disabled.", _human(source))
            summary[source] = {"status": "skipped", "reason": "disabled"}
            continue
        if _is_completed(source):
            logger.info("%s initial backfill already completed, skipping", _human(source))
            summary[source] = {"status": "already_completed"}
            continue
        logger.info(
            "Starting %s initial backfill, limit=%s",
            _human(source),
            settings.INITIAL_BACKFILL_MAX_ITEMS_PER_SOURCE,
        )
        summary[source] = _enqueue_or_run_inline(source)

    if all(entry.get("status") in {"already_completed", "completed", "enqueued", "skipped"} for entry in summary.values()):
        logger.info("Initial backfill completed for all sources")
    return summary


def schedule_initial_backfill_async() -> None:
    """Start the orchestration in a background daemon thread (idempotent)."""

    global _started
    if not settings.INITIAL_BACKFILL_ENABLED or not settings.INITIAL_BACKFILL_RUN_ON_STARTUP:
        logger.info(
            "Initial backfill orchestration skipped (enabled=%s, run_on_startup=%s).",
            settings.INITIAL_BACKFILL_ENABLED,
            settings.INITIAL_BACKFILL_RUN_ON_STARTUP,
        )
        return
    with _lock:
        if _started:
            return
        _started = True

    thread = threading.Thread(
        target=_orchestrate_safely,
        name="initial-backfill-orchestrator",
        daemon=True,
    )
    thread.start()


def _orchestrate_safely() -> None:
    try:
        _orchestrate()
    except Exception as exc:
        logger.exception("Initial backfill orchestration crashed: %s", exc)


def initial_backfill_status() -> dict[str, Any]:
    """Return the current backfill completion status per source."""

    sources: dict[str, dict[str, Any]] = {}
    for source in _HUMAN_NAMES:
        try:
            collector_state = get_collection_state(source, COLLECTOR_STATE_KEY) or {}
            state = get_collection_state(source, INITIAL_BACKFILL_STATE_KEY) or {}
        except Exception:
            collector_state = {}
            state = {}
        completed = bool(collector_state.get("first_run_completed") or state.get("completed"))
        sources[source] = {
            "completed": completed,
            "completed_at": state.get("completed_at") or collector_state.get("last_successful_run_at") or "",
            "total_collected": int(state.get("total_collected") or 0),
            "total_indexed": int(state.get("total_indexed") or 0),
            "total_skipped_existing": int(state.get("total_skipped_existing") or 0),
            "stopped_reason": state.get("stopped_reason") or "",
            "last_cursor": collector_state.get("last_cursor") or "",
            "enabled": _source_enabled(source),
            "name": _human(source),
        }
    all_done = all(
        not item["enabled"] or item["completed"] for item in sources.values()
    )
    return {
        "enabled": settings.INITIAL_BACKFILL_ENABLED,
        "max_items_per_source": settings.INITIAL_BACKFILL_MAX_ITEMS_PER_SOURCE,
        "all_completed": all_done,
        "sources": sources,
    }


def run_initial_backfill_blocking() -> dict[str, Any]:
    """Synchronous entry point for admin endpoints / scripts."""

    return _orchestrate()
