from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from redis import Redis

from app.config import settings


logger = logging.getLogger(__name__)

_KEY_PREFIX = "data_breach_monitor:scan_status:"
_GROUP_KEY = "data_breach_monitor:scan_group:active"
_TTL_SECONDS = 60 * 60 * 24 * 14
SUPPORTED_SOURCES = ("github", "google_alerts", "telegram")
ACTIVE_STATUSES = frozenset({"queued", "running"})
TERMINAL_STATUSES = frozenset({"success", "failed", "cancelled", "timeout", "stale", "warning"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_seconds(started_at: str | None, ended_at: str | None = None) -> float:
    start = _parse_dt(started_at)
    if not start:
        return 0.0
    end = _parse_dt(ended_at) if ended_at else datetime.now(timezone.utc)
    if not end:
        return 0.0
    return max(0.0, (end - start).total_seconds())


def _client() -> Redis:
    return Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )


def _key(source: str) -> str:
    return f"{_KEY_PREFIX}{source}"


def _default_progress() -> dict[str, Any]:
    return {
        "configured_items": 0,
        "processed_items": 0,
        "items_seen": 0,
        "items_collected": 0,
        "items_indexed": 0,
        "duplicates_skipped": 0,
        "skipped_low_confidence": 0,
        "errors": 0,
    }


def _idle_status(source: str) -> dict[str, Any]:
    return {
        "source": source,
        "status": "idle",
        "phase": "idle",
        "task_id": None,
        "run_id": None,
        "scan_group_id": None,
        "requested_mode": None,
        "effective_mode": None,
        "started_at": None,
        "updated_at": None,
        "finished_at": None,
        "duration_seconds": 0,
        "progress": _default_progress(),
        "message": "No active scan",
        "last_error": None,
    }


def _read_raw(source: str) -> dict[str, Any] | None:
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


def _write(source: str, payload: dict[str, Any]) -> None:
    try:
        client = _client()
        client.setex(_key(source), _TTL_SECONDS, json.dumps(payload, default=str))
        group_id = str(payload.get("scan_group_id") or "")
        if group_id and payload.get("status") in ACTIVE_STATUSES:
            client.setex(_GROUP_KEY, _TTL_SECONDS, group_id)
    except Exception as exc:
        logger.warning("Unable to persist scan status for %s: %s", source, exc.__class__.__name__)


def is_source_active(source: str) -> bool:
    payload = _read_raw(source)
    if not payload:
        return False
    return str(payload.get("status") or "") in ACTIVE_STATUSES


def init_scan_run(
    source: str,
    *,
    task_id: str,
    run_id: str,
    scan_group_id: str,
    requested_mode: str,
    effective_mode: str | None = None,
) -> dict[str, Any]:
    started_at = _now()
    payload: dict[str, Any] = {
        "source": source,
        "task_id": task_id,
        "run_id": run_id,
        "scan_group_id": scan_group_id,
        "requested_mode": requested_mode,
        "effective_mode": effective_mode or requested_mode,
        "status": "queued",
        "phase": "queued",
        "started_at": started_at,
        "updated_at": started_at,
        "finished_at": None,
        "duration_seconds": 0,
        "progress": _default_progress(),
        "message": f"{source} scan queued",
        "last_error": None,
        "state": "queued",
        "last_scan_time": started_at,
        "last_scan_result": "queued",
    }
    _write(source, payload)
    return payload


def update_scan_progress(
    source: str,
    *,
    phase: str | None = None,
    status: str | None = None,
    message: str | None = None,
    effective_mode: str | None = None,
    last_error: str | None = None,
    progress: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    existing = _read_raw(source) or _idle_status(source)
    updated_at = _now()
    if phase:
        existing["phase"] = phase
    if status:
        existing["status"] = status
        existing["state"] = status if status in {"queued", "running"} else (
            "completed" if status == "success" else status
        )
    if message is not None:
        existing["message"] = message
    if effective_mode:
        existing["effective_mode"] = effective_mode
    if last_error is not None:
        existing["last_error"] = last_error
    if progress:
        merged = dict(existing.get("progress") or _default_progress())
        merged.update({key: value for key, value in progress.items() if value is not None})
        existing["progress"] = merged
    if extra:
        existing.update(extra)
    existing["updated_at"] = updated_at
    existing["duration_seconds"] = _duration_seconds(
        str(existing.get("started_at") or ""),
        str(existing.get("finished_at") or "") or None,
    )
    existing["last_scan_time"] = updated_at
    _write(source, existing)
    return existing


def mark_scan_running(
    source: str,
    *,
    phase: str = "starting",
    message: str | None = None,
    effective_mode: str | None = None,
) -> None:
    update_scan_progress(
        source,
        status="running",
        phase=phase,
        message=message or f"{source} scan running",
        effective_mode=effective_mode,
    )


def _celery_task_is_active(task_id: str | None) -> bool | None:
    if not task_id:
        return False
    try:
        from app.tasks import celery_app

        inspector = celery_app.control.inspect(timeout=1.0)
        if not inspector:
            return None
        for tasks in (inspector.active() or {}).values():
            if not isinstance(tasks, list):
                continue
            for task in tasks:
                if isinstance(task, dict) and str(task.get("id") or "") == str(task_id):
                    return True
        scheduled = inspector.scheduled() or {}
        reserved = inspector.reserved() or {}
        for bucket in (scheduled, reserved):
            for tasks in bucket.values():
                if not isinstance(tasks, list):
                    continue
                for task in tasks:
                    request = task.get("request") if isinstance(task, dict) else None
                    if isinstance(request, dict) and str(request.get("id") or "") == str(task_id):
                        return True
                    if isinstance(task, dict) and str(task.get("id") or "") == str(task_id):
                        return True
        return False
    except Exception as exc:
        logger.debug("Unable to inspect Celery for task %s: %s", task_id, exc.__class__.__name__)
        return None


def reconcile_stale_status(source: str, payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return payload
    status = str(payload.get("status") or "")
    if status not in ACTIVE_STATUSES:
        return payload

    updated_at = _parse_dt(str(payload.get("updated_at") or ""))
    if not updated_at:
        return payload

    stale_after = timedelta(minutes=max(5, settings.SCAN_STATUS_STALE_MINUTES))
    if datetime.now(timezone.utc) - updated_at <= stale_after:
        return payload

    task_id = str(payload.get("task_id") or "")
    task_active = _celery_task_is_active(task_id or None)
    if task_active is True:
        return payload

    message = "Task appears stale; no recent heartbeat."
    if task_active is False:
        message = "Task appears stale; Celery reports no active worker task."
    mark_scan_failed(source, message, phase="failed", task_id=task_id or None)
    reconciled = _read_raw(source) or payload
    reconciled["status"] = "stale"
    reconciled["phase"] = "failed"
    reconciled["message"] = message
    reconciled["last_error"] = message
    _write(source, reconciled)
    return reconciled


def mark_scan_completed(source: str, result: dict[str, Any]) -> None:
    errors = int(result.get("errors") or 0)
    ended_at = str(result.get("ended_at") or _now())
    indexed = int(result.get("indexed") or result.get("saved") or 0)
    collected = int(result.get("collected") or result.get("messages_collected") or 0)
    duplicates = int(result.get("duplicates_skipped") or 0)
    items_seen = int(result.get("total_seen") or collected)
    started_at = str(result.get("started_at") or "")
    if errors == 0:
        status = "success"
    elif indexed > 0:
        status = "warning"
    else:
        status = "failed"
    progress = {
        "configured_items": int(result.get("configured_items") or 0),
        "processed_items": int(result.get("processed_items") or 0),
        "items_seen": items_seen,
        "items_collected": collected,
        "items_indexed": indexed,
        "duplicates_skipped": duplicates,
        "skipped_low_confidence": int(result.get("skipped_low_confidence") or 0),
        "errors": errors,
    }
    details = result.get("details") if isinstance(result.get("details"), dict) else {}
    source_progress = _source_progress_from_result(source, result, details)
    progress.update(source_progress)

    payload: dict[str, Any] = {
        **result,
        "source": source,
        "status": status,
        "phase": "completed",
        "state": "completed",
        "started_at": started_at,
        "finished_at": ended_at,
        "updated_at": ended_at,
        "duration_seconds": _duration_seconds(started_at, ended_at),
        "progress": progress,
        "message": str(result.get("message") or ("Scan completed successfully" if status == "success" else "Scan completed with errors")),
        "last_error": str(result.get("error") or "") if errors else None,
        "last_scan_time": ended_at,
        "last_scan_result": "completed_with_errors" if errors else "success",
        "indexed_last_scan": indexed,
        "duplicates_skipped": duplicates,
        "errors": errors,
    }
    if result.get("task_id"):
        payload["task_id"] = result["task_id"]
    if result.get("run_id"):
        payload["run_id"] = result["run_id"]
    if result.get("scan_group_id"):
        payload["scan_group_id"] = result["scan_group_id"]
    _write(source, payload)


def mark_scan_failed(
    source: str,
    error: str,
    *,
    phase: str = "failed",
    started_at: str | None = None,
    run_id: str | None = None,
    scan_group_id: str | None = None,
    task_id: str | None = None,
) -> None:
    ended_at = _now()
    existing = _read_raw(source) or {}
    payload = {
        **existing,
        "source": source,
        "status": "failed",
        "phase": phase,
        "state": "failed",
        "started_at": started_at or existing.get("started_at") or ended_at,
        "finished_at": ended_at,
        "updated_at": ended_at,
        "duration_seconds": _duration_seconds(started_at or str(existing.get("started_at") or ""), ended_at),
        "message": error or "Scan failed",
        "last_error": error or "failed",
        "last_scan_time": ended_at,
        "last_scan_result": error or "failed",
        "progress": existing.get("progress") or _default_progress(),
        "indexed_last_scan": 0,
        "duplicates_skipped": 0,
        "errors": 1,
    }
    if run_id:
        payload["run_id"] = run_id
    if scan_group_id:
        payload["scan_group_id"] = scan_group_id
    if task_id:
        payload["task_id"] = task_id
    _write(source, payload)


def _source_progress_from_result(
    source: str,
    result: dict[str, Any],
    details: dict[str, Any],
) -> dict[str, Any]:
    if source == "github":
        validated_types = result.get("validated_secret_types")
        if not isinstance(validated_types, dict):
            validated_types = details.get("validated_secret_types")
        return {
            "queries_total": int(details.get("queries_loaded") or result.get("configured_items") or 0),
            "queries_processed": int(details.get("queries_processed") or result.get("processed_items") or 0),
            "pages_processed": int(details.get("pages_processed") or 0),
            "files_fetched": int(details.get("files_fetched") or 0),
            "skipped_existing": int(result.get("skipped_existing") or details.get("skipped_existing") or 0),
            "skipped_placeholder": int(result.get("skipped_placeholder") or 0),
            "skipped_low_confidence": int(result.get("skipped_low_confidence") or 0),
            "downgraded_template_files": int(result.get("downgraded_template_files") or 0),
            "validated_candidates": int(result.get("validated_candidates") or 0),
            "rejected_placeholders": int(result.get("rejected_placeholders") or 0),
            "rejected_unknown_format": int(result.get("rejected_unknown_format") or 0),
            "validated_secret_types": validated_types if isinstance(validated_types, dict) else {},
            "rate_limit_remaining": details.get("rate_limit_remaining") or details.get("github_rate_limit_remaining"),
        }
    if source == "google_alerts":
        return {
            "feeds_total": int(details.get("feeds_total") or result.get("configured_items") or 0),
            "feeds_processed": int(details.get("feeds_processed") or result.get("processed_items") or 0),
            "entries_seen": int(details.get("rss_entries_collected") or result.get("total_seen") or 0),
            "entries_collected": int(result.get("collected") or 0),
            "entries_indexed": int(result.get("indexed") or 0),
            "known_entries": int(details.get("known_feed_entries") or 0),
            "new_entries": int(details.get("new_feed_entries") or result.get("collected") or 0),
            "latest_published_at": str(details.get("latest_published_at") or result.get("latest_published_at") or ""),
        }
    if source == "telegram":
        return {
            "channels_total": int(details.get("channels_total") or result.get("configured_items") or 0),
            "channels_processed": int(details.get("channels_processed") or result.get("processed_items") or 0),
            "messages_seen": int(details.get("messages_collected") or 0)
            + int(details.get("messages_already_known") or 0),
            "messages_collected": int(result.get("collected") or result.get("messages_collected") or 0),
            "messages_indexed": int(result.get("indexed") or 0),
            "messages_already_known": int(details.get("messages_already_known") or 0),
            "last_message_id": details.get("last_message_id") or result.get("last_message_id"),
            "last_message_date": str(details.get("last_message_date") or result.get("last_message_date") or ""),
        }
    return {}


def _public_view(payload: dict[str, Any] | None, source: str) -> dict[str, Any]:
    if not payload or payload.get("status") == "idle":
        return _idle_status(source)

    progress = dict(payload.get("progress") or _default_progress())
    started_at = payload.get("started_at")
    finished_at = payload.get("finished_at")
    status = str(payload.get("status") or "idle")
    view: dict[str, Any] = {
        "source": source,
        "status": status,
        "phase": str(payload.get("phase") or status),
        "task_id": payload.get("task_id"),
        "run_id": payload.get("run_id"),
        "scan_group_id": payload.get("scan_group_id"),
        "requested_mode": payload.get("requested_mode"),
        "effective_mode": payload.get("effective_mode"),
        "started_at": started_at,
        "updated_at": payload.get("updated_at"),
        "finished_at": finished_at,
        "duration_seconds": payload.get("duration_seconds")
        if payload.get("duration_seconds") is not None
        else _duration_seconds(str(started_at or ""), str(finished_at) if finished_at else None),
        "progress": progress,
        "message": payload.get("message") or "",
        "last_error": payload.get("last_error"),
        "items_seen": int(progress.get("items_seen") or 0),
        "items_collected": int(progress.get("items_collected") or 0),
        "items_indexed": int(progress.get("items_indexed") or 0),
        "duplicates_skipped": int(progress.get("duplicates_skipped") or 0),
        "errors": int(progress.get("errors") or 0),
    }
    for key, value in progress.items():
        if key not in view and value is not None:
            view[key] = value
    return view


def get_scan_status(source: str) -> dict[str, Any] | None:
    return _read_raw(source)


def get_source_live_status(source: str) -> dict[str, Any]:
    raw = reconcile_stale_status(source, _read_raw(source))
    return _public_view(raw, source)


def get_aggregate_scan_status() -> dict[str, Any]:
    sources: dict[str, dict[str, Any]] = {}
    scan_group_id: str | None = None
    any_running = False
    latest_updated: datetime | None = None

    for source in SUPPORTED_SOURCES:
        raw = reconcile_stale_status(source, _read_raw(source))
        view = _public_view(raw, source)
        sources[source] = view
        if view.get("status") in ACTIVE_STATUSES:
            any_running = True
        if not scan_group_id and view.get("scan_group_id"):
            scan_group_id = str(view["scan_group_id"])
        updated = _parse_dt(str(view.get("updated_at") or ""))
        if updated and (latest_updated is None or updated > latest_updated):
            latest_updated = updated

    if not scan_group_id:
        try:
            scan_group_id = _client().get(_GROUP_KEY)
        except Exception:
            scan_group_id = None

    return {
        "scan_group_id": scan_group_id,
        "any_running": any_running,
        "any_active": any_running,
        "updated_at": latest_updated.isoformat() if latest_updated else _now(),
        "sources": sources,
    }


def get_all_scan_statuses(sources: list[str]) -> dict[str, dict[str, Any]]:
    return {source: status for source in sources if (status := get_scan_status(source)) is not None}


def mark_scan_queued(source: str, *, task_id: str | None = None) -> None:
    """Backward-compatible queue marker when run metadata is set separately."""
    existing = _read_raw(source)
    if existing and existing.get("run_id"):
        update_scan_progress(
            source,
            status="queued",
            phase="queued",
            message=f"{source} scan queued",
        )
        return
    run_id = f"{source}-{task_id or 'pending'}"
    init_scan_run(
        source,
        task_id=task_id or "",
        run_id=run_id,
        scan_group_id=run_id,
        requested_mode="incremental",
    )
