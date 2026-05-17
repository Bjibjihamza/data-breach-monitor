from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.collectors.scan_modes import (
    SCAN_MODE_INCREMENTAL,
    is_backfill,
    normalize_scan_mode,
)
from app.config import PROJECT_ROOT, settings
from app.storage.elastic_client import (
    detection_exists_by_telegram_message,
    get_collection_state,
)


logger = logging.getLogger(__name__)

TELEGRAM_SOURCES_PATH = PROJECT_ROOT / "config" / "telegram_sources.yml"


@dataclass(frozen=True)
class TelegramChannelSource:
    name: str
    username: str
    url: str
    category: str
    source_type: str
    limit_per_run: int = 20
    enabled: bool = True


@dataclass(frozen=True)
class TelegramCollectionStats:
    channels_loaded: int = 0
    channels_scanned: int = 0
    messages_collected: int = 0
    new_messages_found: int = 0
    messages_already_known: int = 0
    last_seen_message_id: int = 0
    channel_last_seen_updates: dict[str, int] = field(default_factory=dict)
    errors: int = 0
    skipped_existing: int = 0
    stopped_reason: str = ""
    scan_mode: str = SCAN_MODE_INCREMENTAL
    max_items_per_run: int = 0
    channel_stats: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class TelegramCollectionResult:
    events: list[dict[str, Any]]
    stats: TelegramCollectionStats


def _as_string(value: Any) -> str:
    return str(value or "").strip()


def _as_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_telegram_sources(path: Path = TELEGRAM_SOURCES_PATH) -> list[TelegramChannelSource]:
    if not path.exists():
        logger.warning("Telegram source config does not exist: %s", path)
        return []

    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        logger.warning("Invalid Telegram source YAML at %s: %s", path, exc)
        return []

    raw_channels = payload.get("channels", [])
    if not isinstance(raw_channels, list):
        logger.warning("Telegram source config has no channels list: %s", path)
        return []

    channels: list[TelegramChannelSource] = []
    default_limit_per_channel = max(1, settings.TELEGRAM_LIMIT_PER_CHANNEL)
    for raw_channel in raw_channels:
        if not isinstance(raw_channel, dict):
            continue
        if raw_channel.get("limit_per_run") is None:
            limit_per_run = default_limit_per_channel
        else:
            limit_per_run = max(1, _as_int(raw_channel.get("limit_per_run"), default_limit_per_channel))
        channels.append(
            TelegramChannelSource(
                name=_as_string(raw_channel.get("name")),
                username=_as_string(raw_channel.get("username")),
                url=_as_string(raw_channel.get("url")),
                category=_as_string(raw_channel.get("category")),
                source_type=_as_string(raw_channel.get("source_type")) or "telegram_public_channel",
                limit_per_run=limit_per_run,
                enabled=_as_bool(raw_channel.get("enabled"), True),
            )
        )
    return [channel for channel in channels if channel.enabled]


def inspect_telegram_config(path: Path = TELEGRAM_SOURCES_PATH) -> dict[str, Any]:
    channels = load_telegram_sources(path)
    return {
        "config_file_path": str(path),
        "file_exists": path.exists(),
        "channels_loaded": len(channels),
        "channel_usernames": [channel.username for channel in channels],
        "limits": {
            "default_limit_per_channel": max(1, settings.TELEGRAM_LIMIT_PER_CHANNEL),
            "per_channel": {
                channel.username or channel.name or f"channel_{index}": channel.limit_per_run
                for index, channel in enumerate(channels, start=1)
            },
        },
        "telegram_credentials_present": bool(settings.TELEGRAM_API_ID and settings.TELEGRAM_API_HASH),
        "telegram_api_id_present": bool(settings.TELEGRAM_API_ID),
        "telegram_api_hash_present": bool(settings.TELEGRAM_API_HASH),
        "telegram_session_name": settings.TELEGRAM_SESSION_NAME,
    }


def _message_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return ""


def _message_url(channel: TelegramChannelSource, message_id: int) -> str:
    username = channel.username.lstrip("@")
    if username:
        return f"https://t.me/{username}/{message_id}"
    return channel.url


def _event_from_message(
    channel: TelegramChannelSource,
    message: Any,
    *,
    scan_mode: str,
) -> dict[str, Any] | None:
    text = _as_string(getattr(message, "message", "") or getattr(message, "text", ""))
    if not text:
        return None

    message_id = int(getattr(message, "id", 0) or 0)
    if message_id <= 0:
        return None

    username = channel.username.lstrip("@")
    collected_at = datetime.now(timezone.utc).isoformat()
    return {
        "source": "telegram",
        "signal_type": "telegram_public_channel_message",
        "channel_name": channel.name,
        "channel_username": username,
        "channel_url": channel.url or (f"https://t.me/{username}" if username else ""),
        "message_id": message_id,
        "message_url": _message_url(channel, message_id),
        "text": text,
        "raw_text": text,
        "published_at": _message_datetime(getattr(message, "date", None)),
        "collected_at": collected_at,
        "category": channel.category,
        "source_type": channel.source_type,
        "requires_validation": True,
        "status": "new",
        "scan_mode": scan_mode,
    }


def _credentials_available() -> bool:
    return bool(settings.TELEGRAM_API_ID and settings.TELEGRAM_API_HASH)


def _global_max_items(scan_mode: str) -> int:
    if is_backfill(scan_mode):
        return max(1, settings.INITIAL_BACKFILL_MAX_ITEMS_PER_SOURCE)
    return max(1, settings.TELEGRAM_INCREMENTAL_MAX_ITEMS)


def _per_channel_limit(channel: TelegramChannelSource, scan_mode: str, remaining_budget: int) -> int:
    if is_backfill(scan_mode):
        per_channel = max(channel.limit_per_run, settings.TELEGRAM_LIMIT_PER_CHANNEL)
    else:
        per_channel = channel.limit_per_run
    return max(1, min(per_channel, remaining_budget))


async def _collect_telegram_events_async(
    channels: list[TelegramChannelSource],
    *,
    scan_mode: str,
) -> TelegramCollectionResult:
    global_max_items = _global_max_items(scan_mode)
    try:
        from telethon import TelegramClient
        from telethon.errors import RPCError, SessionPasswordNeededError
    except ImportError:
        logger.error("Telethon is not installed. Rebuild/install dependencies after adding telethon to requirements.txt.")
        return TelegramCollectionResult(
            events=[],
            stats=TelegramCollectionStats(
                channels_loaded=len(channels),
                errors=1,
                scan_mode=scan_mode,
                max_items_per_run=global_max_items,
            ),
        )

    if not _credentials_available():
        logger.error("Telegram API credentials are missing; configure TELEGRAM_API_ID and TELEGRAM_API_HASH.")
        return TelegramCollectionResult(
            events=[],
            stats=TelegramCollectionStats(
                channels_loaded=len(channels),
                errors=1,
                scan_mode=scan_mode,
                max_items_per_run=global_max_items,
            ),
        )

    events: list[dict[str, Any]] = []
    errors = 0
    channels_scanned = 0
    messages_already_known = 0
    skipped_existing = 0
    stopped_reason = ""
    channel_last_seen_updates: dict[str, int] = {}
    channel_stats: list[dict[str, Any]] = []

    client = TelegramClient(
        settings.TELEGRAM_SESSION_NAME,
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
    )

    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.error(
                "Telegram session is not initialized. Run an interactive login once to create the session file."
            )
            await client.disconnect()
            return TelegramCollectionResult(
                events=[],
                stats=TelegramCollectionStats(
                    channels_loaded=len(channels),
                    errors=1,
                    scan_mode=scan_mode,
                    max_items_per_run=global_max_items,
                ),
            )

        for channel in channels:
            if len(events) >= global_max_items:
                stopped_reason = "max_items_per_run_reached"
                logger.info(
                    "[telegram] mode=%s stop reason=%s collected=%s limit=%s",
                    scan_mode,
                    stopped_reason,
                    len(events),
                    global_max_items,
                )
                break

            username = channel.username.lstrip("@")
            if not username:
                logger.info("Skipping Telegram channel '%s': username is missing.", channel.name or "unnamed")
                continue

            remaining = global_max_items - len(events)
            channel_limit = _per_channel_limit(channel, scan_mode, remaining)

            state = get_collection_state("telegram", username)
            last_seen_message_id = int(state.get("last_seen_message_id") or 0)
            try:
                if scan_mode == SCAN_MODE_INCREMENTAL and last_seen_message_id > 0:
                    messages = [
                        message
                        async for message in client.iter_messages(
                            username,
                            limit=channel_limit,
                            min_id=last_seen_message_id,
                            reverse=True,
                        )
                    ]
                else:
                    messages = await client.get_messages(username, limit=channel_limit)
            except (RPCError, ValueError, OSError) as exc:
                errors += 1
                channel_stats.append(
                    {
                        "channel": username,
                        "channel_name": channel.name,
                        "messages_seen": 0,
                        "new_messages": 0,
                        "messages_already_known": 0,
                        "skipped_existing": 0,
                        "last_seen_message_id": last_seen_message_id,
                        "errors": 1,
                    }
                )
                logger.warning(
                    "Skipping Telegram channel '%s': unable to fetch messages (%s).",
                    channel.name or username,
                    exc.__class__.__name__,
                )
                continue

            channels_scanned += 1
            channel_message_count = 0
            channel_seen = 0
            channel_known = 0
            channel_skipped_existing = 0
            newest_message_id = last_seen_message_id
            for message in messages:
                if len(events) >= global_max_items:
                    stopped_reason = "max_items_per_run_reached"
                    break

                message_id = int(getattr(message, "id", 0) or 0)
                if message_id <= 0:
                    continue
                channel_seen += 1
                if scan_mode == SCAN_MODE_INCREMENTAL and last_seen_message_id > 0 and message_id <= last_seen_message_id:
                    messages_already_known += 1
                    channel_known += 1
                    continue
                if detection_exists_by_telegram_message(username, message_id):
                    skipped_existing += 1
                    channel_skipped_existing += 1
                    newest_message_id = max(newest_message_id, message_id)
                    continue

                event = _event_from_message(channel, message, scan_mode=scan_mode)
                if event is None:
                    continue
                events.append(event)
                channel_message_count += 1
                newest_message_id = max(newest_message_id, int(event["message_id"]))

            if newest_message_id > last_seen_message_id:
                channel_last_seen_updates[username] = newest_message_id

            if channel_message_count == 0:
                logger.info("Telegram channel '%s' returned no text messages.", channel.name or username)

            channel_stats.append(
                {
                    "channel": username,
                    "channel_name": channel.name,
                    "messages_seen": channel_seen,
                    "new_messages": channel_message_count,
                    "messages_already_known": channel_known,
                    "skipped_existing": channel_skipped_existing,
                    "last_seen_message_id": newest_message_id,
                    "errors": 0,
                }
            )

            if stopped_reason:
                break

    except SessionPasswordNeededError:
        errors += 1
        logger.error("Telegram login requires two-factor password; complete interactive login before worker scans.")
    except (OSError, ValueError) as exc:
        errors += 1
        logger.error("Telegram scan failed before channel collection: %s", exc)
    finally:
        await client.disconnect()

    return TelegramCollectionResult(
        events=events,
        stats=TelegramCollectionStats(
            channels_loaded=len(channels),
            channels_scanned=channels_scanned,
            messages_collected=len(events),
            new_messages_found=len(events),
            messages_already_known=messages_already_known,
            last_seen_message_id=max(channel_last_seen_updates.values()) if channel_last_seen_updates else 0,
            channel_last_seen_updates=channel_last_seen_updates,
            errors=errors,
            skipped_existing=skipped_existing,
            stopped_reason=stopped_reason,
            scan_mode=scan_mode,
            max_items_per_run=global_max_items,
            channel_stats=channel_stats,
        ),
    )


def collect_telegram_events_with_stats(scan_mode: str | None = None) -> TelegramCollectionResult:
    scan_mode = normalize_scan_mode(scan_mode)
    channels = load_telegram_sources()
    logger.info(
        "[telegram] mode=%s channels_loaded=%s max_items=%s",
        scan_mode,
        len(channels),
        _global_max_items(scan_mode),
    )
    if not channels:
        return TelegramCollectionResult(
            events=[],
            stats=TelegramCollectionStats(scan_mode=scan_mode, max_items_per_run=_global_max_items(scan_mode)),
        )
    return asyncio.run(_collect_telegram_events_async(channels, scan_mode=scan_mode))


def collect_telegram_events(scan_mode: str | None = None) -> list[dict[str, Any]]:
    return collect_telegram_events_with_stats(scan_mode).events
