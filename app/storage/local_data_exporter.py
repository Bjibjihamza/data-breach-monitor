from __future__ import annotations

import json
import logging
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import PROJECT_ROOT, settings
from app.processing.redactor import redact_sensitive_values


logger = logging.getLogger(__name__)

SUPPORTED_SOURCES = ("github", "google_alerts", "telegram")
SOURCE_FILES = {
    "github": "github.jsonl",
    "google_alerts": "google_alerts.jsonl",
    "telegram": "telegram.jsonl",
}
LOCK_TIMEOUT_SECONDS = 15.0
LOCK_POLL_SECONDS = 0.05
MAX_TEXT_EXCERPT_LENGTH = 500
MAX_REDACTED_TEXT_LENGTH = 1000
MAX_SOURCE_TEXT_LENGTH = 1000
SENSITIVE_KEY_RE = re.compile(
    r"\b([A-Z0-9_.-]*(?:PASSWORD|PASSWD|SECRET|TOKEN|KEY|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY|CLIENT[_-]?SECRET|JWT[_-]?SECRET|AUTH[_-]?SECRET|WEBHOOK[_-]?SECRET)[A-Z0-9_.-]*)\s*[:=]\s*(\"[^\"]*\"|'[^']*'|[^\s,;}]+)",
    re.IGNORECASE,
)
JSON_NAME_VALUE_SECRET_RE = re.compile(
    r'("name"\s*:\s*"[A-Z0-9_.-]*(?:PASSWORD|PASSWD|SECRET|TOKEN|KEY|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY|CLIENT[_-]?SECRET|JWT[_-]?SECRET|AUTH[_-]?SECRET|WEBHOOK[_-]?SECRET)[A-Z0-9_.-]*"\s*,\s*"value"\s*:\s*)"[^"]*"',
    re.IGNORECASE,
)
REDACTED_ASSIGNMENT_TAIL_RE = re.compile(r"(\[REDACTED_[A-Z_]+])\S+")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_enabled() -> bool:
    return bool(settings.LOCAL_DATA_EXPORT_ENABLED) and settings.LOCAL_DATA_EXPORT_FORMAT.lower() == "jsonl"


def _export_dir() -> Path:
    configured = Path(settings.LOCAL_DATA_EXPORT_DIR)
    return configured if configured.is_absolute() else PROJECT_ROOT / configured


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def _source_file(source: str) -> Path:
    if source not in SOURCE_FILES:
        raise ValueError(f"unsupported local export source: {source}")
    return _export_dir() / SOURCE_FILES[source]


def ensure_data_files() -> None:
    if not _is_enabled():
        return
    data_dir = _export_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    for source in SUPPORTED_SOURCES:
        _source_file(source).touch(exist_ok=True)


@contextmanager
def _file_lock(source: str) -> Iterator[None]:
    ensure_data_files()
    lock_path = _source_file(source).with_suffix(_source_file(source).suffix + ".lock")
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    lock_fd: int | None = None
    while lock_fd is None:
        try:
            lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(lock_fd, str(os.getpid()).encode("utf-8"))
        except FileExistsError:
            if time.monotonic() >= deadline:
                logger.warning("[local-export] timed out waiting for lock file=%s", _display_path(lock_path))
                break
            time.sleep(LOCK_POLL_SECONDS)
    try:
        yield
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def _optional_text(value: Any) -> str | None:
    cleaned = _text(value)
    return cleaned or None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _redact(value: Any, *, limit: int) -> str:
    text = _text(value)
    if settings.LOCAL_DATA_EXPORT_REDACT:
        text = redact_sensitive_values(text)
        text = JSON_NAME_VALUE_SECRET_RE.sub(r'\1"[REDACTED]"', text)
        text = SENSITIVE_KEY_RE.sub(r"\1=[REDACTED]", text)
        text = REDACTED_ASSIGNMENT_TAIL_RE.sub(r"\1", text)
    return text[:limit]


def _source_item_key(record: dict[str, Any]) -> str:
    for field in ("source_item_key", "item_key", "entry_id"):
        value = _text(record.get(field))
        if value:
            return value
    if _text(record.get("source")) == "telegram" and _text(record.get("channel_username")) and record.get("message_id"):
        return f"telegram:{_text(record.get('channel_username'))}:{_text(record.get('message_id'))}"
    return ""


def _dedup_key(record: dict[str, Any]) -> str:
    detection_hash = _text(record.get("detection_hash"))
    if detection_hash:
        return f"detection_hash:{detection_hash}"
    source_item_key = _source_item_key(record)
    if source_item_key:
        return f"source_item_key:{source_item_key}"
    fallback = "|".join(
        [
            _text(record.get("source")),
            _text(record.get("source_url") or record.get("link") or record.get("message_url")),
            _text(record.get("title")),
            _text(record.get("collected_at")),
        ]
    )
    return f"fallback:{fallback}"


def load_existing_keys(source: str) -> set[str]:
    if not _is_enabled():
        return set()
    ensure_data_files()
    path = _source_file(source)
    keys: set[str] = set()
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    logger.warning("[local-export] skipping corrupt JSONL line source=%s file=%s line=%s", source, _display_path(path), line_number)
                    continue
                if isinstance(record, dict):
                    keys.add(_dedup_key(record))
    except FileNotFoundError:
        ensure_data_files()
    return keys


def _base_record(source: str, record: dict[str, Any], run_context: dict[str, Any]) -> dict[str, Any]:
    now = _utc_now()
    redacted_text = _redact(record.get("redacted_text") or record.get("summary") or record.get("text") or "", limit=MAX_REDACTED_TEXT_LENGTH)
    excerpt = _redact(
        record.get("evidence_excerpt") or record.get("summary") or record.get("text") or redacted_text,
        limit=MAX_TEXT_EXCERPT_LENGTH,
    )
    source_item_key = _source_item_key(record)
    if not source_item_key:
        source_item_key = _text(record.get("source_url") or record.get("message_url") or record.get("title"))
    return {
        "source": source,
        "run_id": _text(record.get("run_id") or run_context.get("run_id")),
        "scan_group_id": _text(record.get("scan_group_id") or run_context.get("scan_group_id")),
        "effective_mode": _text(record.get("effective_mode") or run_context.get("effective_mode") or run_context.get("scan_mode")),
        "detection_hash": _text(record.get("detection_hash")),
        "source_item_key": source_item_key,
        "title": _text(record.get("title")),
        "severity": _text(record.get("severity")),
        "risk_score": _int(record.get("risk_score")),
        "organization": _optional_text(record.get("organization")),
        "source_url": _optional_text(record.get("source_url") or record.get("message_url")),
        "collected_at": _text(record.get("collected_at")),
        "processed_at": _text(record.get("processed_at") or run_context.get("processed_at")),
        "indexed_at": _text(record.get("indexed_at") or now),
        "status": _text(record.get("status") or "new"),
        "text_excerpt": excerpt,
        "redacted_text": redacted_text,
        "created_at": now,
    }


def _github_fields(record: dict[str, Any]) -> dict[str, Any]:
    repository = _text(record.get("repository"))
    repo_owner = _text(record.get("repo_owner"))
    if repository and not repo_owner and "/" in repository:
        repo_owner = repository.split("/", 1)[0]
    organization = record.get("organization")
    if not _text(organization) and repo_owner:
        organization = repo_owner
    evidence = record.get("content_evidence")
    return {
        "repository": _optional_text(repository),
        "repo_owner": _optional_text(repo_owner),
        "file_path": _optional_text(record.get("file_path")),
        "file_sha": _optional_text(record.get("file_sha") or record.get("item_sha")),
        "html_url": _optional_text(record.get("html_url") or record.get("source_url")),
        "raw_url": _optional_text(record.get("raw_url")),
        "query": _optional_text(record.get("query") or record.get("search_query_context")),
        "match_type": _optional_text(record.get("match_type") or record.get("risk_category")),
        "content_evidence": evidence if isinstance(evidence, (dict, list)) else {},
        "path_classification": _optional_text(record.get("path_classification")),
        "evidence_strength": _optional_text(record.get("evidence_strength")),
        "scoring_reason": _optional_text(record.get("scoring_reason")),
    }


def _google_alerts_fields(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "feed_name": _text(record.get("feed_name") or record.get("alert_name")),
        "feed_url": _text(record.get("feed_url")),
        "entry_id": _text(record.get("entry_id") or record.get("source_item_key")),
        "published_at": _text(record.get("published_at")),
        "link": _text(record.get("link") or record.get("source_url")),
        "summary": _redact(record.get("summary"), limit=MAX_SOURCE_TEXT_LENGTH),
    }


def _telegram_fields(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "channel": _text(record.get("channel") or record.get("channel_username")),
        "channel_name": _text(record.get("channel_name")),
        "message_id": _int(record.get("message_id")),
        "message_date": _text(record.get("message_date") or record.get("published_at")),
        "message_url": _text(record.get("message_url") or record.get("source_url")),
        "sender": _text(record.get("sender")),
        "text": _redact(record.get("redacted_text") or record.get("text") or record.get("summary"), limit=MAX_SOURCE_TEXT_LENGTH),
    }


def normalize_record(source: str, record: dict[str, Any], run_context: dict[str, Any]) -> dict[str, Any]:
    normalized = _base_record(source, record, run_context)
    if source == "github":
        normalized.update(_github_fields(record))
    elif source == "google_alerts":
        normalized.update(_google_alerts_fields(record))
    elif source == "telegram":
        normalized.update(_telegram_fields(record))
    return normalized


def append_records(source: str, records: list[dict[str, Any]], run_context: dict[str, Any] | None = None) -> dict[str, Any]:
    received = len(records)
    path = _source_file(source)
    if not _is_enabled():
        return {
            "source": source,
            "enabled": False,
            "received": received,
            "appended": 0,
            "skipped_existing": received,
            "file_path": _display_path(path),
        }

    run_context = run_context or {}
    appended = 0
    skipped_existing = 0
    with _file_lock(source):
        existing_keys = load_existing_keys(source)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            for record in records:
                if not isinstance(record, dict):
                    skipped_existing += 1
                    continue
                normalized = normalize_record(source, record, run_context)
                key = _dedup_key(normalized)
                if key in existing_keys:
                    skipped_existing += 1
                    continue
                handle.write(json.dumps(normalized, ensure_ascii=False, sort_keys=True) + "\n")
                existing_keys.add(key)
                appended += 1
            handle.flush()
            os.fsync(handle.fileno())

    result = {
        "source": source,
        "enabled": True,
        "received": received,
        "appended": appended,
        "skipped_existing": skipped_existing,
        "file_path": _display_path(path),
    }
    logger.info(
        "[local-export] source=%s received=%s appended=%s skipped_existing=%s file=%s",
        source,
        received,
        appended,
        skipped_existing,
        result["file_path"],
    )
    return result


def local_data_export_status() -> dict[str, Any]:
    ensure_data_files()
    files: dict[str, dict[str, Any]] = {}
    for source in SUPPORTED_SOURCES:
        path = _source_file(source)
        exists = path.exists()
        records = 0
        if exists:
            try:
                with path.open("r", encoding="utf-8") as handle:
                    records = sum(1 for line in handle if line.strip())
            except OSError:
                records = 0
        stat = path.stat() if exists else None
        files[source] = {
            "path": _display_path(path),
            "exists": exists,
            "records": records,
            "size_bytes": stat.st_size if stat else 0,
            "last_modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat() if stat else "",
        }
    return {
        "enabled": _is_enabled(),
        "directory": settings.LOCAL_DATA_EXPORT_DIR,
        "format": settings.LOCAL_DATA_EXPORT_FORMAT,
        "redact": settings.LOCAL_DATA_EXPORT_REDACT,
        "files": files,
    }
