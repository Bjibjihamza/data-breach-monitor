from __future__ import annotations

from datetime import datetime, timezone
from datetime import timedelta
from typing import Any, Callable
from uuid import uuid4

from celery import Celery
from celery.signals import worker_ready
from celery.utils.log import get_task_logger

from app.collectors.github_collector import collect_github_events_with_stats
from app.collectors.github_scoring import apply_github_scoring_to_indicators
from app.collectors.google_alerts_collector import collect_google_alert_events_with_stats
from app.collectors.mock_paste_collector import collect_mock_paste_events
from app.collectors.scan_modes import (
    COLLECTOR_STATE_KEY,
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
from app.storage.local_data_exporter import append_records
from app.storage.scan_status import (
    mark_scan_completed,
    mark_scan_failed,
    mark_scan_running,
    update_scan_progress,
)


logger = get_task_logger(__name__)
GITHUB_SCAN_TASK_NAME = "app.tasks.scan_github_task"
STATE_LIST_LIMIT = 5000

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


def _persist_scan_failed(
    source: str,
    error: str,
    *,
    started_at: str | None = None,
    scan_group_id: str | None = None,
    requested_scan_mode: str | None = None,
    effective_scan_mode: str | None = None,
    run_id: str | None = None,
    task_id: str | None = None,
) -> None:
    ended_at = datetime.now(timezone.utc).isoformat()
    mark_scan_failed(
        source,
        error,
        started_at=started_at,
        run_id=run_id,
        scan_group_id=scan_group_id,
        task_id=task_id,
    )
    try:
        save_scan_run_summary(
            source,
            {
                "run_id": run_id or f"{source}-{uuid4().hex}",
                "scan_group_id": scan_group_id,
                "source": source,
                "started_at": started_at or ended_at,
                "ended_at": ended_at,
                "requested_scan_mode": requested_scan_mode,
                "scan_mode": effective_scan_mode or requested_scan_mode,
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


def _merge_unique_strings(new_items: Any, existing_items: Any, *, limit: int = STATE_LIST_LIMIT) -> list[str]:
    merged: list[str] = []
    for collection in (new_items, existing_items):
        if not isinstance(collection, list):
            continue
        for item in collection:
            value = str(item or "").strip()
            if value and value not in merged:
                merged.append(value)
            if len(merged) >= limit:
                return merged
    return merged


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
    collector_state = get_collection_state(source, COLLECTOR_STATE_KEY) or {}
    if collector_state.get("first_run_completed"):
        return True
    state = get_collection_state(source, INITIAL_BACKFILL_STATE_KEY) or {}
    return bool(state.get("completed"))


def _incremental_limit(source: str) -> int:
    if source == "github":
        return max(1, settings.GITHUB_INCREMENTAL_MAX_ITEMS)
    if source == "google_alerts":
        return max(1, settings.GOOGLE_ALERTS_INCREMENTAL_MAX_ITEMS)
    if source == "telegram":
        return max(1, settings.TELEGRAM_INCREMENTAL_MAX_ITEMS)
    return 100


def _resolve_effective_scan_mode(source: str, requested_mode: str | None) -> str:
    requested = normalize_scan_mode(requested_mode)
    if requested == SCAN_MODE_BACKFILL:
        logger.info(
            "[%s] Explicit bootstrap scan requested. limit=%s",
            source,
            settings.INITIAL_BACKFILL_MAX_ITEMS_PER_SOURCE,
        )
        return SCAN_MODE_BACKFILL

    state = get_collection_state(source, COLLECTOR_STATE_KEY) or {}
    if not _backfill_already_completed(source):
        logger.info(
            "[%s] No previous state found. Running bootstrap scan. limit=%s",
            source,
            settings.INITIAL_BACKFILL_MAX_ITEMS_PER_SOURCE,
        )
        return SCAN_MODE_BACKFILL

    logger.info(
        "[%s] Previous state found. Running incremental scan. limit=%s cursor=%s",
        source,
        _incremental_limit(source),
        state.get("last_cursor") or "none",
    )
    return SCAN_MODE_INCREMENTAL


def _state_cursor_from_result(source: str, result: dict[str, Any]) -> str:
    if result.get("last_cursor"):
        return str(result["last_cursor"])
    details = result.get("details") if isinstance(result.get("details"), dict) else {}
    if source == "github":
        return str(details.get("last_cursor") or "")
    if source == "google_alerts":
        return str(details.get("latest_published_at") or "")
    if source == "telegram":
        return str(details.get("last_seen_message_id") or "")
    return ""


def _scan_succeeded_for_state(result: dict[str, Any]) -> bool:
    if bool(result.get("rate_limit_detected") or False):
        return False
    errors = int(result.get("errors") or 0)
    if errors == 0:
        return True
    return int(result.get("indexed") or result.get("saved") or 0) > 0


def _persist_collector_source_state(source: str, result: dict[str, Any], scan_mode: str) -> None:
    if not _scan_succeeded_for_state(result):
        logger.info("[%s] Scan did not complete cleanly; collector state watermark was not advanced.", source)
        return

    existing = get_collection_state(source, COLLECTOR_STATE_KEY) or {}
    ended_at = str(result.get("ended_at") or datetime.now(timezone.utc).isoformat())
    started_at = str(result.get("started_at") or ended_at)
    collected = int(result.get("collected") or result.get("messages_collected") or 0)
    indexed = int(result.get("indexed") or result.get("saved") or 0)
    total_seen = int(result.get("total_seen") or collected)
    state_update = result.get("state_update") if isinstance(result.get("state_update"), dict) else {}
    last_cursor = _state_cursor_from_result(source, result) or str(existing.get("last_cursor") or "")

    payload: dict[str, Any] = {
        **state_update,
        "source": source,
        "first_run_completed": bool(existing.get("first_run_completed"))
        or scan_mode == SCAN_MODE_BACKFILL
        or _backfill_already_completed(source),
        "last_requested_scan_mode": str(result.get("requested_scan_mode") or scan_mode),
        "last_effective_scan_mode": scan_mode,
        "last_started_at": started_at,
        "last_finished_at": ended_at,
        "last_successful_run_at": ended_at,
        "last_cursor": last_cursor,
        "total_items_seen": int(existing.get("total_items_seen") or 0) + total_seen,
        "total_items_processed": int(existing.get("total_items_processed") or 0) + collected,
        "total_items_indexed": int(existing.get("total_items_indexed") or 0) + indexed,
        "updated_at": ended_at,
    }
    if source == "google_alerts" and state_update.get("latest_published_at"):
        payload["latest_published_at"] = state_update["latest_published_at"]
    if source == "telegram":
        if state_update.get("last_message_id"):
            payload["last_message_id"] = state_update["last_message_id"]
        if state_update.get("last_message_date"):
            payload["last_message_date"] = state_update["last_message_date"]
    if source == "github":
        payload["seen_item_keys"] = _merge_unique_strings(
            state_update.get("seen_item_keys"),
            existing.get("seen_item_keys"),
        )
        payload["last_seen_urls"] = _merge_unique_strings(
            state_update.get("last_seen_urls"),
            existing.get("last_seen_urls"),
        )

    _safe_update_collection_state(source, COLLECTOR_STATE_KEY, payload)
    logger.info(
        "[%s] Processed %s new items. Updated cursor=%s",
        source,
        collected,
        last_cursor or "none",
    )


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


def _base_run(
    source_name: str,
    started_at: datetime,
    scan_group_id: str | None = None,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    resolved_run_id = run_id or f"{source_name}-{uuid4().hex}"
    return {
        "run_id": resolved_run_id,
        "scan_group_id": str(scan_group_id or resolved_run_id),
        "source": source_name,
        "started_at": started_at.isoformat(),
    }


def _attach_run_metadata(
    detection: dict[str, Any],
    run: dict[str, Any],
    *,
    requested_mode: str | None,
    effective_mode: str,
) -> dict[str, Any]:
    detection.update(
        {
            "run_id": str(run.get("run_id") or ""),
            "scan_group_id": str(run.get("scan_group_id") or run.get("run_id") or ""),
            "scan_started_at": str(run.get("started_at") or ""),
            "mode_requested": str(requested_mode or effective_mode),
            "effective_mode": str(effective_mode),
        }
    )
    return detection


def _duration(started_at: datetime, ended_at: datetime) -> float:
    return max(0.0, (ended_at - started_at).total_seconds())


def _report_scan_progress(
    source: str,
    phase: str,
    message: str,
    *,
    progress: dict[str, Any] | None = None,
    effective_mode: str | None = None,
) -> None:
    update_scan_progress(
        source,
        status="running",
        phase=phase,
        message=message,
        effective_mode=effective_mode,
        progress=progress,
    )


def _format_task_error(exc: BaseException) -> str:
    return f"{exc.__class__.__name__}: {exc}"[:500]


def _telegram_stat(stats: Any, name: str, default: Any = 0) -> Any:
    value = getattr(stats, name, default)
    if value is None:
        return default
    return value


def _telegram_progress_payload(stats: Any, **overrides: Any) -> dict[str, Any]:
    channels_loaded = int(_telegram_stat(stats, "channels_loaded", 0) or 0)
    channels_processed = int(
        _telegram_stat(stats, "channels_processed", _telegram_stat(stats, "channels_scanned", 0)) or 0
    )
    messages_collected = int(_telegram_stat(stats, "messages_collected", 0) or 0)
    messages_seen = int(_telegram_stat(stats, "messages_seen", 0) or 0)
    payload: dict[str, Any] = {
        "configured_items": channels_loaded,
        "processed_items": channels_processed,
        "channels_total": channels_loaded,
        "channels_processed": channels_processed,
        "channels_with_errors": int(_telegram_stat(stats, "channels_with_errors", 0) or 0),
        "messages_seen": messages_seen,
        "messages_collected": messages_collected,
        "messages_already_known": int(_telegram_stat(stats, "messages_already_known", 0) or 0),
        "last_message_id": _telegram_stat(stats, "last_seen_message_id", 0),
        "last_message_date": str(_telegram_stat(stats, "last_message_date", "") or ""),
        "errors": int(_telegram_stat(stats, "errors", 0) or 0),
    }
    payload.update({key: value for key, value in overrides.items() if value is not None})
    return payload


def _attach_task_metadata(result: dict[str, Any], *, task_id: str | None, run_id: str | None) -> dict[str, Any]:
    if task_id:
        result["task_id"] = task_id
    if run_id:
        result["run_id"] = run_id
    return result


def _export_record_payload(detection: dict[str, Any], raw_event: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(detection)
    raw_event = raw_event or {}
    metadata = raw_event.get("metadata") if isinstance(raw_event.get("metadata"), dict) else {}
    payload["indexed_at"] = datetime.now(timezone.utc).isoformat()
    payload["source_item_key"] = (
        metadata.get("item_key")
        or metadata.get("entry_hash")
        or metadata.get("entry_id")
        or payload.get("source_item_key")
        or ""
    )

    if payload.get("source") == "github":
        repository = str(metadata.get("repository") or "")
        organization = str(payload.get("organization") or "").strip()
        repo_owner = repository.split("/", 1)[0] if "/" in repository else ""
        if not organization and repo_owner:
            organization = repo_owner
        payload.update(
            {
                "repository": repository,
                "repo_owner": repo_owner,
                "organization": organization,
                "file_path": str(metadata.get("file_path") or ""),
                "file_sha": str(metadata.get("item_sha") or ""),
                "html_url": str(metadata.get("html_url") or payload.get("source_url") or ""),
                "raw_url": str(metadata.get("raw_url") or ""),
                "query": str(metadata.get("search_query_context") or payload.get("search_query_context") or ""),
                "match_type": str(metadata.get("risk_category") or payload.get("risk_category") or ""),
                "path_classification": str(payload.get("path_classification") or ""),
                "evidence_strength": str(payload.get("evidence_strength") or ""),
                "scoring_reason": str(payload.get("scoring_reason") or ""),
            }
        )
    elif payload.get("source") == "google_alerts":
        payload.update(
            {
                "feed_name": str(raw_event.get("alert_name") or payload.get("alert_name") or ""),
                "feed_url": str(raw_event.get("feed_url") or metadata.get("feed_url") or ""),
                "entry_id": str(raw_event.get("entry_id") or metadata.get("entry_id") or metadata.get("entry_hash") or ""),
                "link": str(raw_event.get("source_url") or payload.get("source_url") or ""),
            }
        )
    elif payload.get("source") == "telegram":
        payload.update(
            {
                "channel": str(payload.get("channel_username") or raw_event.get("channel_username") or ""),
                "message_date": str(payload.get("published_at") or raw_event.get("published_at") or ""),
                "sender": str(raw_event.get("sender") or ""),
            }
        )
    return payload


def _export_indexed_detections(source: str, detections: list[dict[str, Any]], run: dict[str, Any], scan_mode: str) -> dict[str, Any]:
    run_context = {
        "run_id": run.get("run_id"),
        "scan_group_id": run.get("scan_group_id"),
        "effective_mode": scan_mode,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        return append_records(source, detections, run_context=run_context)
    except Exception as exc:
        logger.warning("[local-export] source=%s failed: %s", source, exc.__class__.__name__)
        return {
            "source": source,
            "enabled": bool(settings.LOCAL_DATA_EXPORT_ENABLED),
            "received": len(detections),
            "appended": 0,
            "skipped_existing": 0,
            "file_path": settings.LOCAL_DATA_EXPORT_DIR,
            "error": exc.__class__.__name__,
        }


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


def _process_github_events(
    scan_mode: str = DEFAULT_SCAN_MODE,
    *,
    requested_mode: str | None = None,
    scan_group_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    source_name = "github"
    scan_mode = normalize_scan_mode(scan_mode)
    requested_mode = normalize_scan_mode(requested_mode or scan_mode)
    started_at = datetime.now(timezone.utc)
    run = _base_run(source_name, started_at, scan_group_id, run_id=run_id)
    logger.info("[%s] SCAN START run=%s mode=%s", source_name, run["run_id"], scan_mode)
    _report_scan_progress(
        source_name,
        "starting",
        "Starting GitHub scan",
        effective_mode=scan_mode,
        progress={"configured_items": 0, "processed_items": 0},
    )
    try:
        _report_scan_progress(source_name, "loading_state", "Loading collector state", effective_mode=scan_mode)
        ensure_index()
    except ElasticsearchUnavailableError as exc:
        logger.error("Skipping %s scan because Elasticsearch is unavailable: %s", source_name, exc)
        ended_at = datetime.now(timezone.utc)
        return {
            **run,
            "scan_mode": scan_mode,
            "requested_scan_mode": requested_mode,
            "effective_mode": scan_mode,
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
        _report_scan_progress(
            source_name,
            "collecting_search_results",
            "Searching GitHub code",
            effective_mode=scan_mode,
        )
        collection = collect_github_events_with_stats(scan_mode=scan_mode)
        _report_scan_progress(
            source_name,
            "fetching_file_contents",
            "Fetching GitHub file contents",
            effective_mode=scan_mode,
            progress={
                "configured_items": collection.stats.queries_loaded,
                "processed_items": collection.stats.queries_processed,
                "items_seen": collection.stats.results_seen,
                "items_collected": len(collection.events),
                "queries_total": collection.stats.queries_loaded,
                "queries_processed": collection.stats.queries_processed,
                "pages_processed": collection.stats.pages_processed,
                "files_fetched": collection.stats.files_fetched,
                "errors": collection.stats.errors,
            },
        )
    except Exception as exc:
        logger.exception("%s collector failed: %s", source_name, exc)
        ended_at = datetime.now(timezone.utc)
        return {
            **run,
            "scan_mode": scan_mode,
            "requested_scan_mode": requested_mode,
            "effective_mode": scan_mode,
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
    skipped_low_confidence = 0
    skipped_placeholder = 0
    downgraded_template_files = 0
    high_confidence_findings = 0
    medium_confidence_findings = 0
    low_confidence_findings = 0
    dropped_placeholder_only = 0
    dropped_template_weak = 0
    dropped_low_confidence = 0
    dropped_no_validated_secret = 0
    dropped_suspicious_path_only = 0
    dropped_duplicate_hash = 0
    indexed_high = 0
    indexed_medium = 0
    exported_jsonl = 0
    not_exported_jsonl = 0
    dropped_existing_source_url = int(collection.stats.skipped_existing or 0)
    dropped_fetch_error = int(collection.stats.content_fetch_failures or 0)
    errors = collection.stats.errors
    exported_detections: list[dict[str, Any]] = []
    validated_secret_types: dict[str, int] = {}
    extracted_candidates = 0
    validated_candidates = 0
    rejected_placeholders = 0
    rejected_unknown_format = 0
    coverage_categories_seen: set[str] = set()
    _report_scan_progress(
        source_name,
        "scoring_findings",
        "Scoring and indexing GitHub findings",
        effective_mode=scan_mode,
        progress={
            "configured_items": collection.stats.queries_loaded,
            "processed_items": collection.stats.queries_processed,
            "items_seen": collection.stats.results_seen,
            "items_collected": len(collection.events),
            "files_fetched": collection.stats.files_fetched,
            "errors": errors,
        },
    )

    for index, raw_event in enumerate(collection.events, start=1):
        try:
            cleaned = clean_text(raw_event.get("raw_text", ""))
            if not cleaned:
                continue

            metadata = raw_event.get("metadata") or {}
            file_path = str(metadata.get("file_path", ""))
            indicators = detect_indicators(
                cleaned,
                organization_hint=raw_event.get("organization"),
                file_path=file_path,
                search_query_context=str(metadata.get("search_query_context", "")),
                risk_category_hint=str(metadata.get("risk_category") or raw_event.get("risk_category") or ""),
                content_only=True,
            )
            github_score = apply_github_scoring_to_indicators(cleaned, file_path, indicators)
            extracted_candidates += int(indicators.get("extracted_secrets_count") or 0)
            validated_candidates += int(indicators.get("validated_secrets_count") or 0)
            rejected_placeholders += int(indicators.get("placeholder_count") or 0)
            rejected_unknown_format += int(indicators.get("rejected_unknown_format") or 0)
            risk_category = str(
                metadata.get("risk_category") or raw_event.get("risk_category") or ""
            ).strip()
            if risk_category:
                coverage_categories_seen.add(risk_category)
            for secret_type in indicators.get("secret_types") or []:
                label = str(secret_type)
                if label:
                    validated_secret_types[label] = validated_secret_types.get(label, 0) + 1

            if github_score.downgraded_template:
                downgraded_template_files += 1

            if not should_store_detection(indicators):
                drop_reason = str(indicators.get("drop_reason") or github_score.drop_reason or "")
                if drop_reason == "placeholder_only":
                    dropped_placeholder_only += 1
                    skipped_placeholder += 1
                elif drop_reason == "template_weak":
                    dropped_template_weak += 1
                elif drop_reason == "suspicious_path_only":
                    dropped_suspicious_path_only += 1
                elif drop_reason == "no_validated_secret":
                    dropped_no_validated_secret += 1
                elif drop_reason == "low_confidence" or github_score.skipped_low_confidence:
                    dropped_low_confidence += 1
                    skipped_low_confidence += 1
                elif github_score.skipped_placeholder:
                    skipped_placeholder += 1
                if indicators.get("is_noise"):
                    skipped_noise += 1
                else:
                    skipped_informational += 1
                continue

            redacted_text = redact_sensitive_values(cleaned)[:1000]
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
            detection = _attach_run_metadata(
                detection,
                run,
                requested_mode=requested_mode,
                effective_mode=scan_mode,
            )
            detection_hash = str(detection["detection_hash"])
            if detection_exists(detection_hash):
                duplicates_skipped += 1
                dropped_duplicate_hash += 1
                logger.info("Skipping duplicate %s detection hash=%s.", source_name, detection_hash)
                continue

            result = save_detection(detection)
            saved += 1
            if severity == "high":
                high_confidence_findings += 1
                indexed_high += 1
            elif severity == "medium":
                medium_confidence_findings += 1
                indexed_medium += 1
            else:
                low_confidence_findings += 1
            if github_score.should_export:
                exported_detections.append(_export_record_payload(detection, raw_event))
                exported_jsonl += 1
            else:
                not_exported_jsonl += 1
            if severity == "high":
                send_telegram_alert(detection)
                send_email_alert(detection)
            logger.info("Saved detection from %s: %s", source_name, result)
            if index % 25 == 0:
                _report_scan_progress(
                    source_name,
                    "indexing_detections",
                    f"Indexed {saved} GitHub detections",
                    effective_mode=scan_mode,
                    progress={
                        "configured_items": collection.stats.queries_loaded,
                        "processed_items": collection.stats.queries_processed,
                        "queries_total": collection.stats.queries_loaded,
                        "queries_processed": collection.stats.queries_processed,
                        "files_fetched": collection.stats.files_fetched,
                        "items_seen": collection.stats.results_seen,
                        "items_collected": len(collection.events),
                        "items_indexed": saved,
                        "duplicates_skipped": duplicates_skipped,
                        "skipped_existing": dropped_existing_source_url,
                        "skipped_low_confidence": skipped_low_confidence,
                        "skipped_placeholder": skipped_placeholder,
                        "downgraded_template_files": downgraded_template_files,
                        "validated_candidates": validated_candidates,
                        "rejected_placeholders": rejected_placeholders,
                        "rejected_unknown_format": rejected_unknown_format,
                        "validated_secret_types": validated_secret_types,
                        "errors": errors,
                    },
                )
        except Exception as exc:
            errors += 1
            logger.exception("Failed to process %s event: %s", source_name, exc)

    ended_at = datetime.now(timezone.utc)
    _report_scan_progress(
        source_name,
        "exporting_jsonl",
        "Exporting GitHub detections to local JSONL",
        effective_mode=scan_mode,
        progress={"items_indexed": saved, "items_collected": len(collection.events), "errors": errors},
    )
    if errors == 0 and not collection.stats.rate_limit_detected and collection.stats.queries_loaded:
        _safe_update_collection_state(
            "github",
            "global_query_rotation",
            {"last_query_index": collection.stats.next_last_query_index},
        )
    logger.info(
        "[github] collected=%s indexed=%s duplicates=%s skipped_noise=%s errors=%s duration=%.2fs "
        "drops(placeholder=%s template_weak=%s low_conf=%s no_secret=%s path_only=%s dup_hash=%s "
        "existing_url=%s fetch_err=%s) indexed(high=%s medium=%s) export(jsonl=%s not=%s)",
        len(collection.events),
        saved,
        duplicates_skipped,
        skipped_noise,
        errors,
        _duration(started_at, ended_at),
        dropped_placeholder_only,
        dropped_template_weak,
        dropped_low_confidence,
        dropped_no_validated_secret,
        dropped_suspicious_path_only,
        dropped_duplicate_hash,
        dropped_existing_source_url,
        dropped_fetch_error,
        indexed_high,
        indexed_medium,
        exported_jsonl,
        not_exported_jsonl,
    )
    local_export = _export_indexed_detections(source_name, exported_detections, run, scan_mode)
    local_export_appended = int(local_export.get("appended") or 0)
    _report_scan_progress(
        source_name,
        "saving_state",
        "Saving GitHub collector state",
        effective_mode=scan_mode,
        progress={"items_indexed": saved, "local_export_appended": local_export_appended},
    )
    return {
        **run,
        "scan_mode": scan_mode,
        "requested_scan_mode": requested_mode,
        "effective_mode": scan_mode,
        "started_at": run["started_at"],
        "collected": len(collection.events),
        "configured_items": collection.stats.queries_loaded,
        "processed_items": collection.stats.queries_processed,
        "duplicates_skipped": duplicates_skipped,
        "indexed": saved,
        "saved": saved,
        "errors": errors,
        "skipped_informational": skipped_informational,
        "skipped_noise": skipped_noise,
        "skipped_low_confidence": skipped_low_confidence,
        "skipped_placeholder": skipped_placeholder,
        "downgraded_template_files": downgraded_template_files,
        "high_confidence_findings": high_confidence_findings,
        "medium_confidence_findings": medium_confidence_findings,
        "low_confidence_findings": low_confidence_findings,
        "dropped_placeholder_only": dropped_placeholder_only,
        "dropped_template_weak": dropped_template_weak,
        "dropped_low_confidence": dropped_low_confidence,
        "dropped_no_validated_secret": dropped_no_validated_secret,
        "dropped_suspicious_path_only": dropped_suspicious_path_only,
        "dropped_duplicate_hash": dropped_duplicate_hash,
        "dropped_existing_source_url": dropped_existing_source_url,
        "dropped_fetch_error": dropped_fetch_error,
        "indexed_high": indexed_high,
        "indexed_medium": indexed_medium,
        "exported_jsonl": exported_jsonl,
        "not_exported_jsonl": not_exported_jsonl,
        "validated_secret_types": validated_secret_types,
        "new_secret_types_detected": sorted(validated_secret_types.keys()),
        "coverage_query_groups_processed": sorted(coverage_categories_seen),
        "extracted_candidates": extracted_candidates,
        "validated_candidates": validated_candidates,
        "rejected_placeholders": rejected_placeholders,
        "rejected_unknown_format": rejected_unknown_format,
        "local_export_appended": local_export_appended,
        "skipped_existing": collection.stats.skipped_existing,
        "total_seen": collection.stats.results_seen,
        "stopped_reason": collection.stats.stopped_reason,
        "rate_limit_detected": collection.stats.rate_limit_detected,
        "last_cursor": collection.stats.last_cursor,
        "state_update": {
            "last_cursor": collection.stats.last_cursor,
            "seen_item_keys": collection.stats.seen_item_keys,
            "last_seen_urls": collection.seen_urls,
        },
        "message": "GitHub scan completed successfully" if errors == 0 else f"GitHub scan completed with {errors} error(s)",
        "local_export": local_export,
        "ended_at": ended_at.isoformat(),
        "duration_seconds": _duration(started_at, ended_at),
        "details": {
            "scan_mode": scan_mode,
            "requested_scan_mode": requested_mode,
            "effective_mode": scan_mode,
            "scan_group_id": run["scan_group_id"],
            "rate_limited": collection.stats.rate_limit_detected,
            "feeds_processed": 0,
            "channels_processed": 0,
            "queries_loaded": collection.stats.queries_loaded,
            "queries_processed": collection.stats.queries_processed,
            "files_fetched": collection.stats.files_fetched,
            "skipped_noise": skipped_noise,
            "skipped_low_confidence": skipped_low_confidence,
            "skipped_placeholder": skipped_placeholder,
            "downgraded_template_files": downgraded_template_files,
            "high_confidence_findings": high_confidence_findings,
            "medium_confidence_findings": medium_confidence_findings,
            "low_confidence_findings": low_confidence_findings,
            "dropped_placeholder_only": dropped_placeholder_only,
            "dropped_template_weak": dropped_template_weak,
            "dropped_low_confidence": dropped_low_confidence,
            "dropped_no_validated_secret": dropped_no_validated_secret,
            "dropped_suspicious_path_only": dropped_suspicious_path_only,
            "dropped_duplicate_hash": dropped_duplicate_hash,
            "dropped_existing_source_url": dropped_existing_source_url,
            "dropped_fetch_error": dropped_fetch_error,
            "indexed_high": indexed_high,
            "indexed_medium": indexed_medium,
            "exported_jsonl": exported_jsonl,
            "not_exported_jsonl": not_exported_jsonl,
            "validated_secret_types": validated_secret_types,
            "new_secret_types_detected": sorted(validated_secret_types.keys()),
            "coverage_query_groups_processed": sorted(coverage_categories_seen),
            "extracted_candidates": extracted_candidates,
            "validated_candidates": validated_candidates,
            "rejected_placeholders": rejected_placeholders,
            "rejected_unknown_format": rejected_unknown_format,
            "local_export_appended": local_export_appended,
            "skipped_existing": collection.stats.skipped_existing,
            "rate_limit_detected": collection.stats.rate_limit_detected,
            "content_fetch_failures": collection.stats.content_fetch_failures,
            "collector_errors": collection.stats.errors,
            "query_window_start": collection.stats.query_window_start,
            "query_window_end": collection.stats.query_window_end,
            "total_query_specs": collection.stats.queries_loaded,
            "pages_processed": collection.stats.pages_processed,
            "results_seen": collection.stats.results_seen,
            "rotated": collection.stats.rotated,
            "last_query_index": collection.stats.next_last_query_index,
            "last_cursor": collection.stats.last_cursor,
            "known_item_keys": collection.stats.known_item_keys,
            "seen_item_keys_count": len(collection.stats.seen_item_keys),
            "max_items_per_run": collection.stats.max_items_per_run,
            "stopped_reason": collection.stats.stopped_reason,
            "local_export": local_export,
            "queries": collection.stats.query_stats,
        },
    }


def _process_google_alerts_events(
    scan_mode: str = DEFAULT_SCAN_MODE,
    *,
    requested_mode: str | None = None,
    scan_group_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    source_name = "google_alerts"
    scan_mode = normalize_scan_mode(scan_mode)
    requested_mode = normalize_scan_mode(requested_mode or scan_mode)
    started_at = datetime.now(timezone.utc)
    run = _base_run(source_name, started_at, scan_group_id, run_id=run_id)
    logger.info("[%s] SCAN START run=%s mode=%s", source_name, run["run_id"], scan_mode)
    _report_scan_progress(source_name, "starting", "Starting Google Alerts scan", effective_mode=scan_mode)
    try:
        _report_scan_progress(source_name, "loading_feeds", "Loading RSS feed configuration", effective_mode=scan_mode)
        ensure_index()
    except ElasticsearchUnavailableError as exc:
        logger.error("Skipping %s scan because Elasticsearch is unavailable: %s", source_name, exc)
        ended_at = datetime.now(timezone.utc)
        return {
            **run,
            "source": source_name,
            "scan_mode": scan_mode,
            "requested_scan_mode": requested_mode,
            "effective_mode": scan_mode,
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

    _report_scan_progress(source_name, "fetching_rss", "Fetching Google Alerts RSS feeds", effective_mode=scan_mode)
    collection = collect_google_alert_events_with_stats(scan_mode=scan_mode)
    _report_scan_progress(
        source_name,
        "parsing_entries",
        "Parsing RSS entries",
        effective_mode=scan_mode,
        progress={
            "configured_items": collection.stats.feeds_loaded,
            "processed_items": collection.stats.feeds_processed,
            "feeds_total": collection.stats.feeds_loaded,
            "feeds_processed": collection.stats.feeds_processed,
            "items_seen": collection.stats.entries_collected + collection.stats.skipped_existing,
            "items_collected": collection.stats.entries_collected,
            "errors": collection.stats.errors,
        },
    )
    saved = 0
    duplicates_skipped = 0
    errors = collection.stats.errors
    exported_detections: list[dict[str, Any]] = []
    _report_scan_progress(
        source_name,
        "indexing_detections",
        "Indexing Google Alerts detections",
        effective_mode=scan_mode,
        progress={"items_collected": collection.stats.entries_collected},
    )

    for raw_event in collection.events:
        try:
            detection = normalize_google_alert_detection(raw_event)
            detection = _attach_run_metadata(
                detection,
                run,
                requested_mode=requested_mode,
                effective_mode=scan_mode,
            )
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
            exported_detections.append(_export_record_payload(detection, raw_event))
            logger.info("Saved Google Alerts public breach news signal: %s", result)
        except Exception as exc:
            errors += 1
            logger.exception("Failed to process Google Alerts event: %s", exc)

    ended_at = datetime.now(timezone.utc)
    if errors == 0:
        for feed_key, known_hashes in collection.stats.feed_state_updates.items():
            partial: dict[str, Any] = {"known_entry_hashes": known_hashes[:200]}
            seen_links = collection.stats.feed_link_state_updates.get(feed_key)
            if seen_links:
                partial["last_seen_links"] = seen_links[:200]
            latest_published_at = collection.stats.feed_published_updates.get(feed_key)
            if latest_published_at:
                partial["latest_published_at"] = latest_published_at
            partial["last_successful_feed_scan_at"] = ended_at.isoformat()
            _safe_update_collection_state("google_alerts", feed_key, partial)
            logger.info(
                "[google_alerts] Feed %s: latest_published_at=%s",
                feed_key,
                partial.get("latest_published_at") or "unchanged",
            )

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

    _report_scan_progress(
        source_name,
        "exporting_jsonl",
        "Exporting Google Alerts detections to local JSONL",
        effective_mode=scan_mode,
        progress={"items_indexed": saved},
    )
    local_export = _export_indexed_detections(source_name, exported_detections, run, scan_mode)
    _report_scan_progress(source_name, "saving_state", "Saving Google Alerts feed state", effective_mode=scan_mode)
    return {
        **run,
        "source": source_name,
        "scan_mode": scan_mode,
        "requested_scan_mode": requested_mode,
        "effective_mode": scan_mode,
        "started_at": run["started_at"],
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
        "last_cursor": collection.stats.latest_published_at,
        "state_update": {
            "last_cursor": collection.stats.latest_published_at,
            "latest_published_at": collection.stats.latest_published_at,
        },
        "message": "No new entries indexed" if saved == 0 and (duplicates_skipped + collection.stats.skipped_existing) > 0 else "Google Alerts scan completed successfully",
        "local_export": local_export,
        "ended_at": ended_at.isoformat(),
        "duration_seconds": _duration(started_at, ended_at),
        "details": {
            "scan_mode": scan_mode,
            "requested_scan_mode": requested_mode,
            "effective_mode": scan_mode,
            "scan_group_id": run["scan_group_id"],
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
            "latest_published_at": collection.stats.latest_published_at,
            "local_export": local_export,
            "feeds": collection.stats.feed_stats,
        },
    }


def _process_telegram_events(
    scan_mode: str = DEFAULT_SCAN_MODE,
    *,
    requested_mode: str | None = None,
    scan_group_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    source_name = "telegram"
    scan_mode = normalize_scan_mode(scan_mode)
    requested_mode = normalize_scan_mode(requested_mode or scan_mode)
    started_at = datetime.now(timezone.utc)
    run = _base_run(source_name, started_at, scan_group_id, run_id=run_id)
    stats: Any = None
    logger.info("[%s] SCAN START run=%s mode=%s", source_name, run["run_id"], scan_mode)
    _report_scan_progress(source_name, "starting", "Starting Telegram scan", effective_mode=scan_mode)
    try:
        _report_scan_progress(
            source_name,
            "loading_channels",
            "Loading Telegram channel configuration",
            effective_mode=scan_mode,
        )
        ensure_index()
    except ElasticsearchUnavailableError as exc:
        logger.error("Skipping %s scan because Elasticsearch is unavailable: %s", source_name, exc)
        ended_at = datetime.now(timezone.utc)
        return {
            **run,
            "source": source_name,
            "scan_mode": scan_mode,
            "requested_scan_mode": requested_mode,
            "effective_mode": scan_mode,
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

    _report_scan_progress(
        source_name,
        "fetching_messages",
        "Fetching Telegram channel messages",
        effective_mode=scan_mode,
    )
    collection = collect_telegram_events_with_stats(scan_mode=scan_mode)
    stats = collection.stats
    indexed = 0
    duplicates_skipped = 0
    errors = int(_telegram_stat(stats, "errors", 0) or 0)
    exported_detections: list[dict[str, Any]] = []
    _report_scan_progress(
        source_name,
        "indexing_detections",
        "Indexing Telegram detections",
        effective_mode=scan_mode,
        progress=_telegram_progress_payload(
            stats,
            items_seen=int(_telegram_stat(stats, "messages_seen", 0) or 0),
            items_collected=int(_telegram_stat(stats, "messages_collected", 0) or 0),
            items_indexed=0,
        ),
    )

    for raw_event in collection.events:
        try:
            detection = normalize_telegram_detection(raw_event)
            detection = _attach_run_metadata(
                detection,
                run,
                requested_mode=requested_mode,
                effective_mode=scan_mode,
            )
            detection_hash = str(detection["detection_hash"])
            if detection_exists(detection_hash):
                duplicates_skipped += 1
                logger.info(
                    "Skipping duplicate Telegram message channel=%s message_id=%s.",
                    detection.get("channel_username") or "unknown",
                    detection.get("message_id") or "unknown",
                )
                continue

            save_detection(detection)
            indexed += 1
            exported_detections.append(_export_record_payload(detection, raw_event))
            logger.info("Saved Telegram OSINT signal from channel=%s", detection.get("channel_username") or "unknown")
        except Exception as exc:
            errors += 1
            logger.exception("Failed to process Telegram event: %s", _format_task_error(exc))

    ended_at = datetime.now(timezone.utc)
    channel_updates = getattr(stats, "channel_last_seen_updates", {}) or {}
    channel_date_updates = getattr(stats, "channel_last_seen_date_updates", {}) or {}
    if isinstance(channel_updates, dict):
        for channel_username, last_seen_message_id in channel_updates.items():
            last_message_date = str(channel_date_updates.get(channel_username, "") or "")
            _safe_update_collection_state(
                "telegram",
                str(channel_username),
                {
                    "last_seen_message_id": int(last_seen_message_id or 0),
                    "last_message_id": int(last_seen_message_id or 0),
                    "last_message_date": last_message_date,
                    "last_successful_scan_at": ended_at.isoformat(),
                },
            )
            logger.info(
                "[telegram] Channel %s: last_message_id=%s last_message_date=%s",
                channel_username,
                last_seen_message_id,
                last_message_date or "unknown",
            )

    channels_loaded = int(_telegram_stat(stats, "channels_loaded", 0) or 0)
    channels_processed = int(
        _telegram_stat(stats, "channels_processed", _telegram_stat(stats, "channels_scanned", 0)) or 0
    )
    channels_with_errors = int(_telegram_stat(stats, "channels_with_errors", 0) or 0)
    messages_collected = int(_telegram_stat(stats, "messages_collected", 0) or 0)
    messages_seen = int(_telegram_stat(stats, "messages_seen", 0) or 0)
    messages_already_known = int(_telegram_stat(stats, "messages_already_known", 0) or 0)
    skipped_existing = int(_telegram_stat(stats, "skipped_existing", 0) or 0)
    last_seen_message_id = int(_telegram_stat(stats, "last_seen_message_id", 0) or 0)
    last_message_date = str(_telegram_stat(stats, "last_message_date", "") or "")
    stopped_reason = str(_telegram_stat(stats, "stopped_reason", "") or "")
    channel_stats = list(getattr(stats, "channel_stats", []) or [])

    logger.info(
        "[telegram] mode=%s channels_loaded=%s channels_processed=%s collected=%s indexed=%s "
        "duplicates=%s skipped_existing=%s errors=%s duration=%.2fs",
        scan_mode,
        channels_loaded,
        channels_processed,
        messages_collected,
        indexed,
        duplicates_skipped,
        skipped_existing,
        errors,
        _duration(started_at, ended_at),
    )

    _report_scan_progress(
        source_name,
        "exporting_jsonl",
        "Exporting Telegram detections to local JSONL",
        effective_mode=scan_mode,
        progress=_telegram_progress_payload(
            stats,
            items_indexed=indexed,
            duplicates_skipped=duplicates_skipped,
        ),
    )
    local_export = _export_indexed_detections(source_name, exported_detections, run, scan_mode)
    _report_scan_progress(
        source_name,
        "saving_state",
        "Saving Telegram channel state",
        effective_mode=scan_mode,
        progress=_telegram_progress_payload(stats, items_indexed=indexed),
    )

    total_seen = messages_seen or (messages_collected + skipped_existing + messages_already_known)
    if indexed == 0 and (duplicates_skipped + skipped_existing) > 0:
        message = "No new channel posts indexed"
    elif errors > 0 and indexed > 0:
        message = f"Telegram scan completed with {errors} error(s)"
    elif errors > 0:
        message = f"Telegram scan completed with {errors} error(s) and no new indexed items"
    else:
        message = "Telegram scan completed successfully"

    return {
        **run,
        "source": source_name,
        "scan_mode": scan_mode,
        "requested_scan_mode": requested_mode,
        "effective_mode": scan_mode,
        "started_at": run["started_at"],
        "configured_items": channels_loaded,
        "processed_items": channels_processed,
        "channels_loaded": channels_loaded,
        "channels_processed": channels_processed,
        "channels_scanned": channels_processed,
        "collected": messages_collected,
        "messages_collected": messages_collected,
        "duplicates_skipped": duplicates_skipped,
        "indexed": indexed,
        "errors": errors,
        "skipped_existing": skipped_existing,
        "total_seen": total_seen,
        "stopped_reason": stopped_reason,
        "last_cursor": str(last_seen_message_id or ""),
        "state_update": {
            "last_cursor": str(last_seen_message_id or ""),
            "last_message_id": last_seen_message_id,
            "last_message_date": last_message_date,
        },
        "message": message,
        "local_export": local_export,
        "ended_at": ended_at.isoformat(),
        "duration_seconds": _duration(started_at, ended_at),
        "details": {
            "scan_mode": scan_mode,
            "requested_scan_mode": requested_mode,
            "effective_mode": scan_mode,
            "scan_group_id": run["scan_group_id"],
            "rate_limited": False,
            "feeds_processed": 0,
            "channels_loaded": channels_loaded,
            "channels_processed": channels_processed,
            "channels_with_errors": channels_with_errors,
            "messages_seen": messages_seen,
            "messages_collected": messages_collected,
            "messages_indexed": indexed,
            "new_messages_found": int(_telegram_stat(stats, "new_messages_found", messages_collected) or 0),
            "messages_already_known": messages_already_known,
            "skipped_existing": skipped_existing,
            "last_seen_message_id": last_seen_message_id,
            "last_message_date": last_message_date,
            "tracked_channels": len(channel_updates) if isinstance(channel_updates, dict) else 0,
            "max_items_per_run": int(_telegram_stat(stats, "max_items_per_run", 0) or 0),
            "stopped_reason": stopped_reason,
            "local_export": local_export,
            "channels": channel_stats,
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
    _persist_collector_source_state(source, result, scan_mode)
    if scan_mode == SCAN_MODE_BACKFILL and _scan_succeeded_for_state(result):
        _mark_initial_backfill_completed(source, result)
    return result


@celery_app.task(bind=True, name="app.tasks.run_google_alerts_scan")
def run_google_alerts_scan(
    self,
    mode: str = DEFAULT_SCAN_MODE,
    scan_group_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, int | str]:
    requested_mode = normalize_scan_mode(mode)
    scan_mode = _resolve_effective_scan_mode("google_alerts", requested_mode)
    task_id = self.request.id
    mark_scan_running("google_alerts", phase="starting", effective_mode=scan_mode)
    try:
        result = _process_google_alerts_events(
            scan_mode,
            requested_mode=requested_mode,
            scan_group_id=scan_group_id,
            run_id=run_id,
        )
    except Exception as exc:
        _persist_scan_failed(
            "google_alerts",
            exc.__class__.__name__,
            scan_group_id=scan_group_id,
            requested_scan_mode=requested_mode,
            effective_scan_mode=scan_mode,
            run_id=run_id,
            task_id=task_id,
        )
        raise
    result["requested_scan_mode"] = requested_mode
    result = _attach_task_metadata(result, task_id=task_id, run_id=run_id or str(result.get("run_id") or ""))
    return _finalize_scan("google_alerts", result, scan_mode)


@celery_app.task(bind=True, name="app.tasks.scan_telegram_channels")
def scan_telegram_channels(
    self,
    mode: str = DEFAULT_SCAN_MODE,
    scan_group_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, int | str]:
    requested_mode = normalize_scan_mode(mode)
    scan_mode = _resolve_effective_scan_mode("telegram", requested_mode)
    task_id = self.request.id
    mark_scan_running("telegram", phase="starting", effective_mode=scan_mode)
    try:
        result = _process_telegram_events(
            scan_mode,
            requested_mode=requested_mode,
            scan_group_id=scan_group_id,
            run_id=run_id,
        )
    except Exception as exc:
        error_message = f"Telegram scan failed: {exc}"[:500]
        _persist_scan_failed(
            "telegram",
            error_message,
            scan_group_id=scan_group_id,
            requested_scan_mode=requested_mode,
            effective_scan_mode=scan_mode,
            run_id=run_id,
            task_id=task_id,
        )
        raise RuntimeError(error_message) from None
    result["requested_scan_mode"] = requested_mode
    result = _attach_task_metadata(result, task_id=task_id, run_id=run_id or str(result.get("run_id") or ""))
    return _finalize_scan("telegram", result, scan_mode)


@celery_app.task(bind=True, name=GITHUB_SCAN_TASK_NAME)
def scan_github_task(
    self,
    mode: str = DEFAULT_SCAN_MODE,
    scan_group_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, int | str]:
    requested_mode = normalize_scan_mode(mode)
    scan_mode = _resolve_effective_scan_mode("github", requested_mode)
    task_id = self.request.id
    mark_scan_running("github", phase="starting", effective_mode=scan_mode)
    try:
        result = _process_github_events(
            scan_mode,
            requested_mode=requested_mode,
            scan_group_id=scan_group_id,
            run_id=run_id,
        )
    except Exception as exc:
        _persist_scan_failed(
            "github",
            f"{exc.__class__.__name__}: {exc}"[:500],
            scan_group_id=scan_group_id,
            requested_scan_mode=requested_mode,
            effective_scan_mode=scan_mode,
            run_id=run_id,
            task_id=task_id,
        )
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
    result["requested_scan_mode"] = requested_mode
    result = _attach_task_metadata(result, task_id=task_id, run_id=run_id or str(result.get("run_id") or ""))
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
