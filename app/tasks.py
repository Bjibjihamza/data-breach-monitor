from __future__ import annotations

from datetime import datetime, timezone
from datetime import timedelta
from typing import Any, Callable
from uuid import uuid4

from celery import Celery
from celery.signals import worker_ready
from celery.utils.log import get_task_logger

from app.collectors.github_collector import collect_github_events_with_stats
from app.collectors.google_alerts_collector import collect_google_alert_events_with_stats
from app.collectors.mock_paste_collector import collect_mock_paste_events
from app.collectors.scan_modes import (
    DEFAULT_SCAN_MODE,
    INITIAL_BACKFILL_STATE_KEY,
    LAST_RUN_STATE_KEY,
    SCAN_MODE_BACKFILL,
    SCAN_MODE_INCREMENTAL,
    is_backfill,
    normalize_scan_mode,
)
from app.collectors.telegram_collector import collect_telegram_events_with_stats
from app.config import settings
from app.processing.google_alerts import normalize_google_alert_detection
from app.processing.telegram import normalize_telegram_detection
from app.processing.cleaner import clean_text
from app.processing.deduplicator import add_detection_hash
from app.processing.detector import detect_indicators, should_store_detection
from app.processing.normalizer import normalize_detection
from app.processing.redactor import redact_sensitive_values
from app.processing.scorer import compute_confidence, score_detection
from app.alerts.email_alert import send_email_alert
from app.alerts.telegram_alert import send_telegram_alert
from app.storage.elastic_client import (
    ElasticsearchUnavailableError,
    detection_exists,
    ensure_index,
    get_collection_state,
    save_detection,
    save_scan_run_summary,
    update_collection_state,
    upsert_collection_state,
    wait_for_elasticsearch,
)
from app.storage.scan_status import mark_scan_completed, mark_scan_failed, mark_scan_running


logger = get_task_logger(__name__)
GITHUB_SCAN_TASK_NAME = "app.tasks.scan_github_task"

celery_app = Celery(
    "data_breach_monitor",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks"],
)

celery_app.conf.timezone = "UTC"
celery_app.conf.beat_schedule = {
    "google-alerts-scan": {
        "task": "app.tasks.run_google_alerts_scan",
        "schedule": timedelta(minutes=settings.GOOGLE_ALERTS_INTERVAL_MINUTES),
    },
    "github-scan": {
        "task": GITHUB_SCAN_TASK_NAME,
        "schedule": timedelta(minutes=settings.GITHUB_INTERVAL_MINUTES),
    },
    "telegram-scan": {
        "task": "app.tasks.scan_telegram_channels",
        "schedule": timedelta(minutes=settings.TELEGRAM_INTERVAL_MINUTES),
    },
}


Collector = Callable[[], list[dict[str, Any]]]


def _persist_scan_completed(source: str, result: dict[str, Any]) -> None:
    mark_scan_completed(source, result)
    try:
        save_scan_run_summary(source, result)
    except Exception as exc:
        logger.warning("Unable to persist %s scan summary in Elasticsearch: %s", source, exc.__class__.__name__)


def _persist_scan_failed(source: str, error: str, *, started_at: str | None = None) -> None:
    ended_at = datetime.now(timezone.utc).isoformat()
    mark_scan_failed(source, error)
    try:
        save_scan_run_summary(
            source,
            {
                "run_id": f"{source}-{uuid4().hex}",
                "source": source,
                "started_at": started_at or ended_at,
                "ended_at": ended_at,
                "status": "error",
                "collected": 0,
                "indexed": 0,
                "duplicates_skipped": 0,
                "skipped_noise": 0,
                "skipped_informational": 0,
                "errors": 1,
                "message": error or "failed",
                "details": {},
            },
        )
    except Exception as exc:
        logger.warning("Unable to persist failed %s scan summary in Elasticsearch: %s", source, exc.__class__.__name__)


def _safe_update_collection_state(source: str, key: str, partial_state: dict[str, Any]) -> None:
    try:
        update_collection_state(source, key, partial_state)
    except Exception as exc:
        logger.warning("Unable to update collection state for %s/%s: %s", source, key, exc.__class__.__name__)


def _persist_last_run_state(source: str, result: dict[str, Any]) -> None:
    """Persist a compact summary of the last collection run for ``source``."""

    ended_at = str(result.get("ended_at") or datetime.now(timezone.utc).isoformat())
    started_at = str(result.get("started_at") or ended_at)
    errors = int(result.get("errors") or 0)
    scan_mode = normalize_scan_mode(result.get("scan_mode"))
    payload: dict[str, Any] = {
        "scan_mode": scan_mode,
        "last_run_at": ended_at,
        "started_at": started_at,
        "total_collected": int(result.get("collected") or result.get("messages_collected") or 0),
        "total_seen": int(result.get("total_seen") or 0),
        "total_skipped_existing": int(result.get("skipped_existing") or 0),
        "total_indexed": int(result.get("indexed") or result.get("saved") or 0),
        "duplicates_skipped": int(result.get("duplicates_skipped") or 0),
        "errors": errors,
        "stopped_reason": str(result.get("stopped_reason") or ""),
        "rate_limit_detected": bool(result.get("rate_limit_detected") or False),
    }
    if errors == 0:
        payload["last_success_at"] = ended_at
        payload["error"] = ""
    else:
        payload["error"] = str(result.get("error") or "errors_during_scan")
    _safe_update_collection_state(source, LAST_RUN_STATE_KEY, payload)


def _mark_initial_backfill_completed(source: str, result: dict[str, Any]) -> None:
    completed_at = str(result.get("ended_at") or datetime.now(timezone.utc).isoformat())
    payload = {
        "completed": True,
        "completed_at": completed_at,
        "scan_mode": SCAN_MODE_BACKFILL,
        "total_collected": int(result.get("collected") or result.get("messages_collected") or 0),
        "total_indexed": int(result.get("indexed") or result.get("saved") or 0),
        "total_skipped_existing": int(result.get("skipped_existing") or 0),
        "stopped_reason": str(result.get("stopped_reason") or ""),
    }
    _safe_update_collection_state(source, INITIAL_BACKFILL_STATE_KEY, payload)


def _backfill_already_completed(source: str) -> bool:
    state = get_collection_state(source, INITIAL_BACKFILL_STATE_KEY) or {}
    return bool(state.get("completed"))


@worker_ready.connect
def _wait_for_elasticsearch_on_worker_start(sender: Any = None, **_: Any) -> None:
    try:
        wait_for_elasticsearch()
    except ElasticsearchUnavailableError:
        logger.error("Worker started but Elasticsearch is not reachable yet; scan tasks may fail until ES is up.")


@worker_ready.connect
def _log_registered_tasks(sender: Any = None, **_: Any) -> None:
    app = getattr(sender, "app", celery_app)
    registered_tasks = sorted(name for name in app.tasks if name.startswith("app.tasks."))
    logger.info(
        "Registered data breach monitor Celery tasks: %s",
        ", ".join(registered_tasks) or "none",
    )
    if GITHUB_SCAN_TASK_NAME in app.tasks:
        logger.info("GitHub Celery task registered: %s", GITHUB_SCAN_TASK_NAME)
    else:
        logger.error("GitHub Celery task is not registered: expected %s", GITHUB_SCAN_TASK_NAME)


def _base_run(source_name: str, started_at: datetime) -> dict[str, Any]:
    return {
        "run_id": f"{source_name}-{uuid4().hex}",
        "source": source_name,
        "started_at": started_at.isoformat(),
    }


def _duration(started_at: datetime, ended_at: datetime) -> float:
    return max(0.0, (ended_at - started_at).total_seconds())


def _process_events(source_name: str, collector: Collector) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    errors = 0
    run = _base_run(source_name, started_at)
    logger.info("[%s] SCAN START run=%s", source_name, run["run_id"])
    try:
        ensure_index()
    except ElasticsearchUnavailableError as exc:
        logger.error("Skipping %s scan because Elasticsearch is unavailable: %s", source_name, exc)
        ended_at = datetime.now(timezone.utc)
        return {
            **run,
            "source": source_name,
            "collected": 0,
            "duplicates_skipped": 0,
            "indexed": 0,
            "saved": 0,
            "errors": 1,
            "error": "elasticsearch_unavailable",
            "ended_at": ended_at.isoformat(),
            "duration_seconds": _duration(started_at, ended_at),
        }

    try:
        raw_events = collector()
    except Exception as exc:
        logger.exception("%s collector failed: %s", source_name, exc)
        ended_at = datetime.now(timezone.utc)
        return {
            **run,
            "source": source_name,
            "collected": 0,
            "duplicates_skipped": 0,
            "indexed": 0,
            "saved": 0,
            "errors": 1,
            "ended_at": ended_at.isoformat(),
            "duration_seconds": _duration(started_at, ended_at),
        }

    saved = 0
    duplicates_skipped = 0
    skipped_informational = 0
    skipped_noise = 0

    for raw_event in raw_events:
        try:
            cleaned = clean_text(raw_event.get("raw_text", ""))
            if not cleaned:
                continue

            metadata = raw_event.get("metadata") or {}
            content_only = raw_event.get("source") == "github"
            indicators = detect_indicators(
                cleaned,
                organization_hint=raw_event.get("organization"),
                file_path=str(metadata.get("file_path", "")),
                search_query_context=str(metadata.get("search_query_context", "")),
                risk_category_hint=str(
                    metadata.get("risk_category") or raw_event.get("risk_category") or ""
                ),
                content_only=content_only,
            )
            if not should_store_detection(indicators):
                if indicators.get("is_noise"):
                    skipped_noise += 1
                else:
                    skipped_informational += 1
                result_name = raw_event.get("title") or raw_event.get("source_url") or source_name
                logger.info(
                    "Ignored %s result %s. Reason: %s. Validated secrets: %s. Placeholder count: %s",
                    source_name,
                    result_name,
                    indicators.get("noise_reason") or indicators.get("final_decision") or "not actionable",
                    indicators.get("validated_secrets_count", 0),
                    indicators.get("placeholder_count", 0),
                )
                continue

            redacted_text = redact_sensitive_values(cleaned)
            score, severity = score_detection(raw_event, indicators)
            confidence = compute_confidence(indicators)
            detection = normalize_detection(
                raw_event=raw_event,
                clean_text=cleaned,
                indicators=indicators,
                redacted_text=redacted_text,
                score=score,
                severity=severity,
                confidence=confidence,
            )
            detection = add_detection_hash(detection)
            detection_hash = str(detection["detection_hash"])
            if detection_exists(detection_hash):
                duplicates_skipped += 1
                logger.info("Skipping duplicate %s detection hash=%s.", source_name, detection_hash)
                continue

            result = save_detection(detection)
            saved += 1
            if severity == "high":
                send_telegram_alert(detection)
                send_email_alert(detection)
            logger.info("Saved detection from %s: %s", source_name, result)
            print(f"Saved detection from {source_name}: {result}")
        except Exception as exc:
            errors += 1
            logger.exception("Failed to process %s event: %s", source_name, exc)

    ended_at = datetime.now(timezone.utc)
    logger.info(
        "[%s] SCAN END run=%s collected=%s indexed=%s duplicates=%s skipped_noise=%s errors=%s duration=%.2fs",
        source_name,
        run["run_id"],
        len(raw_events),
        saved,
        duplicates_skipped,
        skipped_noise,
        errors,
        _duration(started_at, ended_at),
    )

    return {
        **run,
        "source": source_name,
        "collected": len(raw_events),
        "duplicates_skipped": duplicates_skipped,
        "indexed": saved,
        "saved": saved,
        "errors": errors,
        "skipped_informational": skipped_informational,
        "skipped_noise": skipped_noise,
        "ended_at": ended_at.isoformat(),
        "duration_seconds": _duration(started_at, ended_at),
    }


def _process_github_events(scan_mode: str = DEFAULT_SCAN_MODE) -> dict[str, Any]:
    source_name = "github"
    scan_mode = normalize_scan_mode(scan_mode)
    started_at = datetime.now(timezone.utc)
    run = _base_run(source_name, started_at)
    logger.info("[%s] SCAN START run=%s mode=%s", source_name, run["run_id"], scan_mode)
    try:
        ensure_index()
    except ElasticsearchUnavailableError as exc:
        logger.error("Skipping %s scan because Elasticsearch is unavailable: %s", source_name, exc)
        ended_at = datetime.now(timezone.utc)
        return {
            **run,
            "scan_mode": scan_mode,
            "collected": 0,
            "duplicates_skipped": 0,
            "indexed": 0,
            "saved": 0,
            "errors": 1,
            "error": "elasticsearch_unavailable",
            "ended_at": ended_at.isoformat(),
            "duration_seconds": _duration(started_at, ended_at),
            "details": {"rate_limited": False, "feeds_processed": 0, "channels_processed": 0, "scan_mode": scan_mode},
        }

    try:
        collection = collect_github_events_with_stats(scan_mode=scan_mode)
    except Exception as exc:
        logger.exception("%s collector failed: %s", source_name, exc)
        ended_at = datetime.now(timezone.utc)
        return {
            **run,
            "scan_mode": scan_mode,
            "collected": 0,
            "duplicates_skipped": 0,
            "indexed": 0,
            "saved": 0,
            "errors": 1,
            "ended_at": ended_at.isoformat(),
            "duration_seconds": _duration(started_at, ended_at),
            "details": {"rate_limited": False, "feeds_processed": 0, "channels_processed": 0, "scan_mode": scan_mode},
        }

    logger.info(
        "[github] run=%s queries_loaded=%s processed=%s",
        run["run_id"],
        collection.stats.queries_loaded,
        collection.stats.queries_processed,
    )

    saved = 0
    duplicates_skipped = 0
    skipped_informational = 0
    skipped_noise = 0
    errors = 0

    for raw_event in collection.events:
        try:
            cleaned = clean_text(raw_event.get("raw_text", ""))
            if not cleaned:
                continue

            metadata = raw_event.get("metadata") or {}
            indicators = detect_indicators(
                cleaned,
                organization_hint=raw_event.get("organization"),
                file_path=str(metadata.get("file_path", "")),
                search_query_context=str(metadata.get("search_query_context", "")),
                risk_category_hint=str(metadata.get("risk_category") or raw_event.get("risk_category") or ""),
                content_only=True,
            )
            if not should_store_detection(indicators):
                if indicators.get("is_noise"):
                    skipped_noise += 1
                else:
                    skipped_informational += 1
                continue

            redacted_text = redact_sensitive_values(cleaned)
            score, severity = score_detection(raw_event, indicators)
            confidence = compute_confidence(indicators)
            detection = normalize_detection(
                raw_event=raw_event,
                clean_text=cleaned,
                indicators=indicators,
                redacted_text=redacted_text,
                score=score,
                severity=severity,
                confidence=confidence,
            )
            detection = add_detection_hash(detection)
            detection_hash = str(detection["detection_hash"])
            if detection_exists(detection_hash):
                duplicates_skipped += 1
                logger.info("Skipping duplicate %s detection hash=%s.", source_name, detection_hash)
                continue

            result = save_detection(detection)
            saved += 1
            if severity == "high":
                send_telegram_alert(detection)
                send_email_alert(detection)
            logger.info("Saved detection from %s: %s", source_name, result)
        except Exception as exc:
            errors += 1
            logger.exception("Failed to process %s event: %s", source_name, exc)

    ended_at = datetime.now(timezone.utc)
    if errors == 0 and not collection.stats.rate_limit_detected and collection.stats.queries_loaded:
        _safe_update_collection_state(
            "github",
            "global_query_rotation",
            {"last_query_index": collection.stats.next_last_query_index},
        )
    logger.info(
        "[github] collected=%s indexed=%s duplicates=%s skipped_noise=%s errors=%s duration=%.2fs",
        len(collection.events),
        saved,
        duplicates_skipped,
        skipped_noise,
        errors,
        _duration(started_at, ended_at),
    )
    return {
        **run,
        "scan_mode": scan_mode,
        "collected": len(collection.events),
        "configured_items": collection.stats.queries_loaded,
        "processed_items": collection.stats.queries_processed,
        "duplicates_skipped": duplicates_skipped,
        "indexed": saved,
        "saved": saved,
        "errors": errors,
        "skipped_informational": skipped_informational,
        "skipped_noise": skipped_noise,
        "skipped_existing": collection.stats.skipped_existing,
        "total_seen": collection.stats.results_seen,
        "stopped_reason": collection.stats.stopped_reason,
        "rate_limit_detected": collection.stats.rate_limit_detected,
        "message": "GitHub scan completed successfully" if errors == 0 else f"GitHub scan completed with {errors} error(s)",
        "ended_at": ended_at.isoformat(),
        "duration_seconds": _duration(started_at, ended_at),
        "details": {
            "scan_mode": scan_mode,
            "rate_limited": collection.stats.rate_limit_detected,
            "feeds_processed": 0,
            "channels_processed": 0,
            "queries_loaded": collection.stats.queries_loaded,
            "queries_processed": collection.stats.queries_processed,
            "files_fetched": collection.stats.files_fetched,
            "skipped_noise": skipped_noise,
            "skipped_existing": collection.stats.skipped_existing,
            "rate_limit_detected": collection.stats.rate_limit_detected,
            "content_fetch_failures": collection.stats.content_fetch_failures,
            "query_window_start": collection.stats.query_window_start,
            "query_window_end": collection.stats.query_window_end,
            "total_query_specs": collection.stats.queries_loaded,
            "pages_processed": collection.stats.pages_processed,
            "results_seen": collection.stats.results_seen,
            "rotated": collection.stats.rotated,
            "last_query_index": collection.stats.next_last_query_index,
            "max_items_per_run": collection.stats.max_items_per_run,
            "stopped_reason": collection.stats.stopped_reason,
            "queries": collection.stats.query_stats,
        },
    }


def _process_google_alerts_events(scan_mode: str = DEFAULT_SCAN_MODE) -> dict[str, Any]:
    source_name = "google_alerts"
    scan_mode = normalize_scan_mode(scan_mode)
    started_at = datetime.now(timezone.utc)
    run = _base_run(source_name, started_at)
    logger.info("[%s] SCAN START run=%s mode=%s", source_name, run["run_id"], scan_mode)
    try:
        ensure_index()
    except ElasticsearchUnavailableError as exc:
        logger.error("Skipping %s scan because Elasticsearch is unavailable: %s", source_name, exc)
        ended_at = datetime.now(timezone.utc)
        return {
            **run,
            "source": source_name,
            "scan_mode": scan_mode,
            "collected": 0,
            "duplicates_skipped": 0,
            "indexed": 0,
            "saved": 0,
            "errors": 1,
            "error": "elasticsearch_unavailable",
            "ended_at": ended_at.isoformat(),
            "duration_seconds": _duration(started_at, ended_at),
            "details": {
                "scan_mode": scan_mode,
                "rate_limited": False,
                "feeds_processed": 0,
                "channels_processed": 0,
            },
        }

    collection = collect_google_alert_events_with_stats(scan_mode=scan_mode)
    saved = 0
    duplicates_skipped = 0
    errors = collection.stats.errors

    for raw_event in collection.events:
        try:
            detection = normalize_google_alert_detection(raw_event)
            detection_hash = str(detection["detection_hash"])
            if detection_exists(detection_hash):
                duplicates_skipped += 1
                logger.info(
                    "Skipping duplicate Google Alerts entry '%s' from alert '%s'.",
                    detection.get("title") or detection.get("source_url") or "untitled",
                    detection.get("alert_name") or "unknown",
                )
                continue

            result = save_detection(detection)
            saved += 1
            logger.info("Saved Google Alerts public breach news signal: %s", result)
        except Exception as exc:
            errors += 1
            logger.exception("Failed to process Google Alerts event: %s", exc)

    ended_at = datetime.now(timezone.utc)
    if errors == collection.stats.errors:
        for feed_key, known_hashes in collection.stats.feed_state_updates.items():
            partial: dict[str, Any] = {"known_entry_hashes": known_hashes[:200]}
            seen_links = collection.stats.feed_link_state_updates.get(feed_key)
            if seen_links:
                partial["last_seen_links"] = seen_links[:200]
            partial["last_successful_feed_scan_at"] = ended_at.isoformat()
            _safe_update_collection_state("google_alerts", feed_key, partial)

    logger.info(
        "[google_alerts] feeds_loaded=%s valid=%s feeds_processed=%s",
        collection.stats.feeds_loaded,
        collection.stats.valid_rss_urls,
        collection.stats.feeds_processed,
    )
    if scan_mode == SCAN_MODE_BACKFILL:
        logger.info(
            "Google Alerts backfill completed: collected=%s, skipped_existing=%s",
            saved,
            collection.stats.skipped_existing,
        )
    else:
        logger.info(
            "[google_alerts] mode=%s collected=%s indexed=%s duplicates=%s skipped_existing=%s errors=%s duration=%.2fs",
            scan_mode,
            collection.stats.entries_collected,
            saved,
            duplicates_skipped,
            collection.stats.skipped_existing,
            errors,
            _duration(started_at, ended_at),
        )

    return {
        **run,
        "source": source_name,
        "scan_mode": scan_mode,
        "configured_items": collection.stats.feeds_loaded,
        "processed_items": collection.stats.feeds_processed,
        "feeds_loaded": collection.stats.feeds_loaded,
        "valid_rss_urls": collection.stats.valid_rss_urls,
        "feeds_processed": collection.stats.feeds_processed,
        "skipped_missing_rss": collection.stats.skipped_missing_rss,
        "skipped_placeholder_rss": collection.stats.skipped_placeholder_rss,
        "skipped_invalid_rss_url": collection.stats.skipped_invalid_rss_url,
        "skipped_invalid_structure": collection.stats.skipped_invalid_structure,
        "collected": collection.stats.entries_collected,
        "duplicates_skipped": duplicates_skipped,
        "indexed": saved,
        "saved": saved,
        "errors": errors,
        "config_error": collection.stats.config_error,
        "skipped_existing": collection.stats.skipped_existing,
        "total_seen": collection.stats.entries_collected + collection.stats.skipped_existing,
        "stopped_reason": collection.stats.stopped_reason,
        "message": "No new entries indexed" if saved == 0 and (duplicates_skipped + collection.stats.skipped_existing) > 0 else "Google Alerts scan completed successfully",
        "ended_at": ended_at.isoformat(),
        "duration_seconds": _duration(started_at, ended_at),
        "details": {
            "scan_mode": scan_mode,
            "rate_limited": False,
            "feeds_loaded": collection.stats.feeds_loaded,
            "valid_feeds": collection.stats.valid_rss_urls,
            "feeds_processed": collection.stats.feeds_processed,
            "rss_entries_collected": collection.stats.entries_collected,
            "feeds_with_errors": collection.stats.errors,
            "new_feed_entries": collection.stats.new_feed_entries,
            "known_feed_entries": collection.stats.known_feed_entries,
            "skipped_existing": collection.stats.skipped_existing,
            "tracked_feeds": len(collection.stats.feed_state_updates),
            "channels_processed": 0,
            "max_items_per_run": collection.stats.max_items_per_run,
            "stopped_reason": collection.stats.stopped_reason,
            "feeds": collection.stats.feed_stats,
        },
    }


def _process_telegram_events(scan_mode: str = DEFAULT_SCAN_MODE) -> dict[str, Any]:
    source_name = "telegram"
    scan_mode = normalize_scan_mode(scan_mode)
    started_at = datetime.now(timezone.utc)
    run = _base_run(source_name, started_at)
    logger.info("[%s] SCAN START run=%s mode=%s", source_name, run["run_id"], scan_mode)
    try:
        ensure_index()
    except ElasticsearchUnavailableError as exc:
        logger.error("Skipping %s scan because Elasticsearch is unavailable: %s", source_name, exc)
        ended_at = datetime.now(timezone.utc)
        return {
            **run,
            "source": source_name,
            "scan_mode": scan_mode,
            "collected": 0,
            "messages_collected": 0,
            "duplicates_skipped": 0,
            "indexed": 0,
            "errors": 1,
            "error": "elasticsearch_unavailable",
            "ended_at": ended_at.isoformat(),
            "duration_seconds": _duration(started_at, ended_at),
            "details": {
                "scan_mode": scan_mode,
                "rate_limited": False,
                "feeds_processed": 0,
                "channels_processed": 0,
            },
        }

    collection = collect_telegram_events_with_stats(scan_mode=scan_mode)
    indexed = 0
    duplicates_skipped = 0
    errors = collection.stats.errors

    for raw_event in collection.events:
        try:
            detection = normalize_telegram_detection(raw_event)
            detection_hash = str(detection["detection_hash"])
            if detection_exists(detection_hash):
                duplicates_skipped += 1
                logger.info(
                    "Skipping duplicate Telegram message channel=%s message_id=%s.",
                    detection.get("channel_username") or "unknown",
                    detection.get("message_id") or "unknown",
                )
                continue

            result = save_detection(detection)
            indexed += 1
            logger.info("Saved Telegram OSINT signal: %s", result)
        except Exception as exc:
            errors += 1
            logger.exception("Failed to process Telegram event: %s", exc)

    ended_at = datetime.now(timezone.utc)
    if errors == collection.stats.errors:
        for channel_username, last_seen_message_id in collection.stats.channel_last_seen_updates.items():
            _safe_update_collection_state(
                "telegram",
                channel_username,
                {
                    "last_seen_message_id": last_seen_message_id,
                    "last_successful_scan_at": ended_at.isoformat(),
                },
            )

    if scan_mode == SCAN_MODE_BACKFILL:
        logger.info(
            "Telegram backfill completed: collected=%s, skipped_existing=%s",
            indexed,
            collection.stats.skipped_existing,
        )
    else:
        logger.info(
            "[telegram] mode=%s channels=%s collected=%s indexed=%s duplicates=%s skipped_existing=%s errors=%s duration=%.2fs",
            scan_mode,
            collection.stats.channels_loaded,
            collection.stats.messages_collected,
            indexed,
            duplicates_skipped,
            collection.stats.skipped_existing,
            errors,
            _duration(started_at, ended_at),
        )

    return {
        **run,
        "source": source_name,
        "scan_mode": scan_mode,
        "configured_items": collection.stats.channels_loaded,
        "processed_items": collection.stats.channels_scanned,
        "channels_loaded": collection.stats.channels_loaded,
        "channels_scanned": collection.stats.channels_scanned,
        "collected": collection.stats.messages_collected,
        "messages_collected": collection.stats.messages_collected,
        "duplicates_skipped": duplicates_skipped,
        "indexed": indexed,
        "errors": errors,
        "skipped_existing": collection.stats.skipped_existing,
        "total_seen": collection.stats.messages_collected + collection.stats.skipped_existing + collection.stats.messages_already_known,
        "stopped_reason": collection.stats.stopped_reason,
        "message": "No new channel posts indexed" if indexed == 0 and (duplicates_skipped + collection.stats.skipped_existing) > 0 else "Telegram scan completed successfully",
        "ended_at": ended_at.isoformat(),
        "duration_seconds": _duration(started_at, ended_at),
        "details": {
            "scan_mode": scan_mode,
            "rate_limited": False,
            "feeds_processed": 0,
            "channels_loaded": collection.stats.channels_loaded,
            "channels_processed": collection.stats.channels_scanned,
            "messages_collected": collection.stats.messages_collected,
            "new_messages_found": collection.stats.new_messages_found,
            "messages_already_known": collection.stats.messages_already_known,
            "skipped_existing": collection.stats.skipped_existing,
            "last_seen_message_id": collection.stats.last_seen_message_id,
            "tracked_channels": len(collection.stats.channel_last_seen_updates),
            "channels_with_errors": collection.stats.errors,
            "max_items_per_run": collection.stats.max_items_per_run,
            "stopped_reason": collection.stats.stopped_reason,
            "channels": collection.stats.channel_stats,
        },
    }


@celery_app.task(name="app.tasks.run_mock_paste_scan")
def run_mock_paste_scan() -> dict[str, int | str]:
    mark_scan_running("mock_paste")
    try:
        result = _process_events("mock_paste", collect_mock_paste_events)
    except Exception as exc:
        _persist_scan_failed("mock_paste", exc.__class__.__name__)
        raise
    _persist_scan_completed("mock_paste", result)
    return result


def _finalize_scan(source: str, result: dict[str, Any], scan_mode: str) -> dict[str, Any]:
    _persist_scan_completed(source, result)
    _persist_last_run_state(source, result)
    if scan_mode == SCAN_MODE_BACKFILL and int(result.get("errors") or 0) == 0:
        _mark_initial_backfill_completed(source, result)
    return result


@celery_app.task(name="app.tasks.run_google_alerts_scan")
def run_google_alerts_scan(mode: str = DEFAULT_SCAN_MODE) -> dict[str, int | str]:
    scan_mode = normalize_scan_mode(mode)
    mark_scan_running("google_alerts")
    try:
        result = _process_google_alerts_events(scan_mode)
    except Exception as exc:
        _persist_scan_failed("google_alerts", exc.__class__.__name__)
        raise
    return _finalize_scan("google_alerts", result, scan_mode)


@celery_app.task(name="app.tasks.scan_telegram_channels")
def scan_telegram_channels(mode: str = DEFAULT_SCAN_MODE) -> dict[str, int | str]:
    scan_mode = normalize_scan_mode(mode)
    mark_scan_running("telegram")
    try:
        result = _process_telegram_events(scan_mode)
    except Exception as exc:
        _persist_scan_failed("telegram", exc.__class__.__name__)
        raise
    return _finalize_scan("telegram", result, scan_mode)


@celery_app.task(name=GITHUB_SCAN_TASK_NAME)
def scan_github_task(mode: str = DEFAULT_SCAN_MODE) -> dict[str, int | str]:
    scan_mode = normalize_scan_mode(mode)
    mark_scan_running("github")
    try:
        result = _process_github_events(scan_mode)
    except Exception as exc:
        _persist_scan_failed("github", exc.__class__.__name__)
        raise
    collected = int(result.get("collected", 0))
    indexed = int(result.get("indexed", result.get("saved", 0)))
    duplicates_skipped = int(result.get("duplicates_skipped", 0))
    skipped_existing = int(result.get("skipped_existing", 0))
    errors = int(result.get("errors", 0))
    if scan_mode == SCAN_MODE_BACKFILL:
        logger.info(
            "GitHub backfill completed: collected=%s, skipped_existing=%s",
            indexed,
            skipped_existing,
        )
    else:
        logger.info(
            "GitHub scan summary: mode=%s collected=%s duplicates_skipped=%s skipped_existing=%s indexed=%s errors=%s",
            scan_mode,
            collected,
            duplicates_skipped,
            skipped_existing,
            indexed,
            errors,
        )
    return _finalize_scan("github", result, scan_mode)


@celery_app.task(name="app.tasks.run_initial_backfill")
def run_initial_backfill() -> dict[str, Any]:
    """Run the one-time initial backfill across every external source.

    Sources that already have ``initial_backfill_completed`` recorded in
    Elasticsearch are skipped. Each remaining source is invoked in
    ``backfill`` mode and bounded by ``INITIAL_BACKFILL_MAX_ITEMS_PER_SOURCE``.
    """

    logger.info("Initial backfill check started")
    if not settings.INITIAL_BACKFILL_ENABLED:
        logger.info("INITIAL_BACKFILL_ENABLED=false; skipping initial backfill orchestration.")
        return {"started": False, "reason": "disabled", "results": {}}

    plan = [
        ("github", scan_github_task, bool(settings.GITHUB_TOKEN)),
        ("google_alerts", run_google_alerts_scan, True),
        ("telegram", scan_telegram_channels, bool(settings.TELEGRAM_API_ID and settings.TELEGRAM_API_HASH)),
    ]
    summary: dict[str, dict[str, Any]] = {}

    for source, task_callable, enabled in plan:
        if not enabled:
            logger.info("Skipping %s initial backfill: source is disabled (missing credentials).", source)
            summary[source] = {"status": "skipped", "reason": "disabled"}
            continue
        if _backfill_already_completed(source):
            logger.info("%s initial backfill already completed, skipping", _human_source(source))
            summary[source] = {"status": "already_completed"}
            continue

        logger.info(
            "Starting %s initial backfill, limit=%s",
            _human_source(source),
            settings.INITIAL_BACKFILL_MAX_ITEMS_PER_SOURCE,
        )
        try:
            result = task_callable.run(mode=SCAN_MODE_BACKFILL)  # type: ignore[union-attr]
        except Exception as exc:
            logger.exception("%s initial backfill failed: %s", source, exc)
            summary[source] = {"status": "error", "error": exc.__class__.__name__}
            continue
        summary[source] = {
            "status": "completed",
            "collected": int(result.get("collected") or result.get("messages_collected") or 0),
            "indexed": int(result.get("indexed") or result.get("saved") or 0),
            "skipped_existing": int(result.get("skipped_existing") or 0),
            "errors": int(result.get("errors") or 0),
        }

    logger.info("Initial backfill completed for all sources: %s", summary)
    return {"started": True, "results": summary}


def _human_source(source: str) -> str:
    return {
        "github": "GitHub",
        "google_alerts": "Google Alerts",
        "telegram": "Telegram",
    }.get(source, source)


run_github_scan = scan_github_task
