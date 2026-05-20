from __future__ import annotations

import calendar
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup

from app.collectors.scan_modes import (
    SCAN_MODE_INCREMENTAL,
    is_backfill,
    normalize_scan_mode,
)
from app.config import PROJECT_ROOT, settings
from app.storage.elastic_client import (
    detection_exists_by_source_url,
    get_collection_state,
)


logger = logging.getLogger(__name__)

GOOGLE_ALERTS_FEEDS_PATH = PROJECT_ROOT / "config" / "google_alerts_feeds.yml"
RSS_PLACEHOLDER = "PASTE_RSS_URL_HERE"
REQUEST_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class GoogleAlertsFeed:
    alert_name: str
    category: str
    country: str
    organizations: list[str] = field(default_factory=list)
    query: str = ""
    rss_url: str = ""


@dataclass(frozen=True)
class GoogleAlertsCollectionStats:
    feeds_loaded: int = 0
    valid_rss_urls: int = 0
    feeds_processed: int = 0
    skipped_missing_rss: int = 0
    skipped_placeholder_rss: int = 0
    skipped_invalid_rss_url: int = 0
    skipped_invalid_structure: int = 0
    entries_collected: int = 0
    known_feed_entries: int = 0
    new_feed_entries: int = 0
    feed_state_updates: dict[str, list[str]] = field(default_factory=dict)
    feed_link_state_updates: dict[str, list[str]] = field(default_factory=dict)
    feed_published_updates: dict[str, str] = field(default_factory=dict)
    errors: int = 0
    config_error: str = ""
    skipped_existing: int = 0
    stopped_reason: str = ""
    scan_mode: str = SCAN_MODE_INCREMENTAL
    max_items_per_run: int = 0
    latest_published_at: str = ""
    feed_stats: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class GoogleAlertsCollectionResult:
    events: list[dict[str, Any]]
    stats: GoogleAlertsCollectionStats


def _as_string(value: Any) -> str:
    return str(value or "").strip()


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_as_string(item) for item in value if _as_string(item)]


def _rss_url_skip_reason(rss_url: str) -> str:
    if not rss_url:
        return "missing"
    if rss_url == RSS_PLACEHOLDER:
        return "placeholder"
    if not rss_url.lower().startswith("http"):
        return "invalid"
    return ""


def _is_valid_rss_url(rss_url: str) -> bool:
    return _rss_url_skip_reason(rss_url) == ""


def _load_google_alerts_yaml(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        message = f"Google Alerts feed config does not exist: {path}"
        logger.warning(message)
        return {}, message

    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        message = f"Invalid Google Alerts feed YAML at {path}: {exc}"
        logger.exception(message)
        return {}, message

    if not isinstance(payload, dict):
        message = f"Google Alerts feed config root must be a mapping: {path}"
        logger.warning(message)
        return {}, message

    return payload, ""


def _select_raw_google_alerts_feeds(payload: dict[str, Any]) -> tuple[str, Any]:
    for key in ("feeds", "alerts", "google_alerts_feeds"):
        if key in payload:
            return key, payload.get(key)
    return "", []


def _feed_from_raw(raw_feed: Any) -> GoogleAlertsFeed | None:
    if not isinstance(raw_feed, dict):
        return None
    return GoogleAlertsFeed(
        alert_name=_as_string(raw_feed.get("alert_name")),
        category=_as_string(raw_feed.get("category")),
        country=_as_string(raw_feed.get("country")),
        organizations=_as_string_list(raw_feed.get("organizations")),
        query=_as_string(raw_feed.get("query")),
        rss_url=_as_string(raw_feed.get("rss_url")),
    )


def inspect_google_alerts_config(path: Path = GOOGLE_ALERTS_FEEDS_PATH) -> dict[str, Any]:
    payload, parse_error = _load_google_alerts_yaml(path)
    top_level_keys = list(payload.keys()) if isinstance(payload, dict) else []
    selected_key, raw_feeds = _select_raw_google_alerts_feeds(payload)
    invalid_structure = 0
    feeds: list[GoogleAlertsFeed] = []

    if raw_feeds and not isinstance(raw_feeds, list):
        invalid_structure += 1
        raw_feeds_list: list[Any] = []
    else:
        raw_feeds_list = raw_feeds if isinstance(raw_feeds, list) else []

    for raw_feed in raw_feeds_list:
        feed = _feed_from_raw(raw_feed)
        if feed is None:
            invalid_structure += 1
            continue
        feeds.append(feed)

    missing_rss = 0
    placeholder_rss = 0
    invalid_rss_url = 0
    valid_feeds: list[GoogleAlertsFeed] = []
    for feed in feeds:
        reason = _rss_url_skip_reason(feed.rss_url)
        if reason == "missing":
            missing_rss += 1
        elif reason == "placeholder":
            placeholder_rss += 1
        elif reason == "invalid":
            invalid_rss_url += 1
        else:
            valid_feeds.append(feed)

    return {
        "config_file_path": str(path),
        "file_exists": path.exists(),
        "top_level_yaml_keys": top_level_keys,
        "selected_feed_key": selected_key,
        "feeds_count": len(feeds),
        "feeds_loaded": len(feeds),
        "valid_feeds_count": len(valid_feeds),
        "valid_feeds": len(valid_feeds),
        "invalid_feeds": missing_rss + placeholder_rss + invalid_rss_url + invalid_structure,
        "skipped_missing_rss_url": missing_rss,
        "skipped_placeholder_rss_url": placeholder_rss,
        "skipped_invalid_rss_url": invalid_rss_url,
        "skipped_invalid_structure": invalid_structure,
        "feed_names": [feed.alert_name for feed in feeds],
        "first_5_feed_names": [feed.alert_name for feed in feeds[:5]],
        "first_5_rss_url_previews": [
            f"{feed.rss_url[:48]}..." if len(feed.rss_url) > 48 else feed.rss_url
            for feed in feeds[:5]
        ],
        "max_entries_per_feed": max(1, settings.GOOGLE_ALERTS_MAX_ENTRIES_PER_FEED),
        "max_feeds_per_run": max(1, settings.GOOGLE_ALERTS_MAX_FEEDS_PER_RUN),
        "parse_error": parse_error,
    }


def load_google_alerts_feeds(path: Path = GOOGLE_ALERTS_FEEDS_PATH) -> list[GoogleAlertsFeed]:
    diagnostics = inspect_google_alerts_config(path)
    logger.info("Google Alerts config loaded from %s", diagnostics["config_file_path"])
    logger.info("Google Alerts config file exists: %s", "yes" if diagnostics["file_exists"] else "no")
    logger.info("Google Alerts top-level keys: %s", ", ".join(diagnostics["top_level_yaml_keys"]) or "none")
    logger.info("Google Alerts selected feed key: %s", diagnostics["selected_feed_key"] or "none")
    logger.info("Google Alerts feeds found before filtering: %s", diagnostics["feeds_count"])
    logger.info("Google Alerts valid RSS feeds: %s", diagnostics["valid_feeds_count"])
    logger.info(
        (
            "Google Alerts feeds skipped: missing_rss_url=%s placeholder_rss_url=%s "
            "invalid_rss_url=%s invalid_structure=%s"
        ),
        diagnostics["skipped_missing_rss_url"],
        diagnostics["skipped_placeholder_rss_url"],
        diagnostics["skipped_invalid_rss_url"],
        diagnostics["skipped_invalid_structure"],
    )
    if diagnostics["parse_error"]:
        logger.warning("Google Alerts config parse error: %s", diagnostics["parse_error"])
        return []

    payload, _ = _load_google_alerts_yaml(path)
    _, raw_feeds = _select_raw_google_alerts_feeds(payload)
    if not isinstance(raw_feeds, list):
        logger.warning("Google Alerts feed list has invalid structure in %s", path)
        return []

    feeds: list[GoogleAlertsFeed] = []
    for raw_feed in raw_feeds:
        feed = _feed_from_raw(raw_feed)
        if feed is None:
            continue
        feeds.append(feed)
    return feeds


def _clean_summary(value: str) -> str:
    if not value:
        return ""
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


def _entry_datetime(entry: Any) -> str:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), timezone.utc).isoformat()
    value = _as_string(entry.get("published") or entry.get("updated"))
    return value


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _is_newer_than(value: str, watermark: str) -> bool:
    parsed_value = _parse_datetime(value)
    parsed_watermark = _parse_datetime(watermark)
    if parsed_value is None or parsed_watermark is None:
        return False
    return parsed_value > parsed_watermark


def _latest_datetime(current: str, candidate: str) -> str:
    if not candidate:
        return current
    if not current:
        return candidate
    return candidate if _is_newer_than(candidate, current) else current


def _entry_source(entry: Any, feed: Any) -> str:
    source = entry.get("source")
    if isinstance(source, dict):
        title = _as_string(source.get("title"))
        if title:
            return title
    return _as_string((getattr(feed, "feed", {}) or {}).get("title"))


def _feed_state_key(feed_config: GoogleAlertsFeed) -> str:
    return feed_config.alert_name or feed_config.query or feed_config.rss_url[:120] or "unnamed_feed"


def _entry_hash(feed_config: GoogleAlertsFeed, entry: Any) -> str:
    raw = "|".join(
        [
            _feed_state_key(feed_config),
            _as_string(entry.get("id") or entry.get("guid")),
            _as_string(entry.get("link")),
            _clean_summary(_as_string(entry.get("title"))),
            _entry_datetime(entry),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _fetch_feed(rss_url: str, alert_name: str) -> Any | None:
    try:
        response = requests.get(
            rss_url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": "DataBreachMonitor/0.2 GoogleAlertsRSS"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning(
            "Skipping Google Alerts feed '%s': RSS fetch failed (%s).",
            alert_name,
            exc.__class__.__name__,
        )
        return None

    parsed = feedparser.parse(response.content)
    if parsed.bozo:
        logger.warning("Google Alerts feed '%s' parsed with warning: %s", alert_name, parsed.bozo_exception)
    return parsed


def _event_from_entry(
    feed_config: GoogleAlertsFeed,
    parsed_feed: Any,
    entry: Any,
    *,
    entry_hash: str,
    scan_mode: str,
) -> dict[str, Any]:
    title = _clean_summary(_as_string(entry.get("title"))) or "Google Alert"
    summary = _clean_summary(_as_string(entry.get("summary") or entry.get("description")))
    link = _as_string(entry.get("link"))
    collected_at = datetime.now(timezone.utc).isoformat()

    return {
        "source": "google_alerts",
        "signal_type": "public_breach_news",
        "alert_name": feed_config.alert_name,
        "category": feed_config.category,
        "country": feed_config.country,
        "organizations": feed_config.organizations,
        "query": feed_config.query,
        "title": title,
        "summary": summary,
        "source_url": link,
        "feed_url": feed_config.rss_url,
        "entry_id": entry_hash,
        "published_at": _entry_datetime(entry),
        "collected_at": collected_at,
        "source_name": _entry_source(entry, parsed_feed),
        "raw_text": f"{title}\n{summary}".strip(),
        "scan_mode": scan_mode,
        "metadata": {
            "alert_name": feed_config.alert_name,
            "category": feed_config.category,
            "country": feed_config.country,
            "organizations": feed_config.organizations,
            "query": feed_config.query,
            "source_name": _entry_source(entry, parsed_feed),
            "feed_state_key": _feed_state_key(feed_config),
            "feed_url": feed_config.rss_url,
            "entry_hash": entry_hash,
            "entry_id": entry_hash,
            "scan_mode": scan_mode,
        },
    }


def _global_max_items(scan_mode: str) -> int:
    if is_backfill(scan_mode):
        return max(1, settings.INITIAL_BACKFILL_MAX_ITEMS_PER_SOURCE)
    return max(1, settings.GOOGLE_ALERTS_INCREMENTAL_MAX_ITEMS)


def collect_google_alert_events_with_stats(scan_mode: str | None = None) -> GoogleAlertsCollectionResult:
    scan_mode = normalize_scan_mode(scan_mode)
    diagnostics = inspect_google_alerts_config()
    feeds = load_google_alerts_feeds()
    valid_feeds = [feed for feed in feeds if _is_valid_rss_url(feed.rss_url)]
    max_feeds = max(1, settings.GOOGLE_ALERTS_MAX_FEEDS_PER_RUN)
    max_entries_per_feed = max(1, settings.GOOGLE_ALERTS_MAX_ENTRIES_PER_FEED)
    global_max_items = _global_max_items(scan_mode)
    feeds_to_process = valid_feeds[:max_feeds]
    skipped_missing_rss = int(diagnostics["skipped_missing_rss_url"])
    skipped_placeholder_rss = int(diagnostics["skipped_placeholder_rss_url"])
    skipped_invalid_rss_url = int(diagnostics["skipped_invalid_rss_url"])
    skipped_invalid_structure = int(diagnostics["skipped_invalid_structure"])
    events: list[dict[str, Any]] = []
    known_feed_entries = 0
    new_feed_entries = 0
    skipped_existing = 0
    stopped_reason = ""
    feed_state_updates: dict[str, list[str]] = {}
    feed_link_state_updates: dict[str, list[str]] = {}
    feed_published_updates: dict[str, str] = {}
    latest_published_at = ""
    feed_stats: list[dict[str, Any]] = []

    logger.info(
        (
            "[google_alerts] mode=%s max_items_per_run=%s feeds_loaded=%s valid_rss_urls=%s feeds_to_process=%s "
            "skipped: missing_rss=%s placeholder_rss=%s invalid_rss=%s invalid_structure=%s max_entries_per_feed=%s"
        ),
        scan_mode,
        global_max_items,
        len(feeds),
        len(valid_feeds),
        len(feeds_to_process),
        skipped_missing_rss,
        skipped_placeholder_rss,
        skipped_invalid_rss_url,
        skipped_invalid_structure,
        max_entries_per_feed,
    )
    if len(valid_feeds) > max_feeds:
        logger.info(
            "Google Alerts max feed limit reached; processing first %s of %s valid feed(s).",
            max_feeds,
            len(valid_feeds),
        )

    errors = 0
    for feed_config in feeds:
        skip_reason = _rss_url_skip_reason(feed_config.rss_url)
        if skip_reason:
            logger.info(
                "Skipping Google Alerts feed '%s': rss_url is %s.",
                feed_config.alert_name or "unnamed",
                skip_reason,
            )

    feeds_processed_count = 0
    for feed_config in feeds_to_process:
        if len(events) >= global_max_items:
            stopped_reason = "max_items_per_run_reached"
            logger.info(
                "[google_alerts] mode=%s stop reason=%s collected=%s limit=%s",
                scan_mode,
                stopped_reason,
                len(events),
                global_max_items,
            )
            break

        parsed_feed = _fetch_feed(feed_config.rss_url, feed_config.alert_name)
        feeds_processed_count += 1
        if parsed_feed is None:
            errors += 1
            feed_stats.append(
                {
                    "feed": feed_config.alert_name or feed_config.query or "unnamed_feed",
                    "category": feed_config.category,
                    "entries_seen": 0,
                    "known_entries": 0,
                    "new_entries": 0,
                    "skipped_existing": 0,
                    "errors": 1,
                }
            )
            continue

        feed_entries = getattr(parsed_feed, "entries", []) or []
        limited_entries = feed_entries[:max_entries_per_feed]
        feed_known = 0
        feed_new = 0
        feed_skipped_existing = 0
        if len(feed_entries) > max_entries_per_feed:
            logger.info(
                "Google Alerts max entries per feed reached for '%s': processing %s of %s entries.",
                feed_config.alert_name or "unnamed",
                max_entries_per_feed,
                len(feed_entries),
            )
        feed_key = _feed_state_key(feed_config)
        feed_state = get_collection_state("google_alerts", feed_key)
        known_hashes = [
            str(item)
            for item in feed_state.get("known_entry_hashes", [])
            if item
        ] if isinstance(feed_state.get("known_entry_hashes"), list) else []
        known_links = [
            str(item)
            for item in feed_state.get("last_seen_links", [])
            if item
        ] if isinstance(feed_state.get("last_seen_links"), list) else []
        known_hash_set = set(known_hashes)
        known_link_set = set(known_links)
        observed_hashes: list[str] = []
        observed_links: list[str] = []
        previous_latest_published_at = _as_string(feed_state.get("latest_published_at"))
        feed_latest_published_at = previous_latest_published_at
        cursor_reached = False
        if previous_latest_published_at:
            logger.info(
                "[google_alerts] Feed %s: latest_published_at=%s",
                feed_config.alert_name or feed_key,
                previous_latest_published_at,
            )

        for entry in limited_entries:
            if len(events) >= global_max_items:
                stopped_reason = "max_items_per_run_reached"
                logger.info(
                    "[google_alerts] mode=%s stop reason=%s collected=%s limit=%s",
                    scan_mode,
                    stopped_reason,
                    len(events),
                    global_max_items,
                )
                break

            entry_hash = _entry_hash(feed_config, entry)
            entry_link = _as_string(entry.get("link"))
            entry_published_at = _entry_datetime(entry)
            observed_hashes.append(entry_hash)
            if entry_link:
                observed_links.append(entry_link)
            feed_latest_published_at = _latest_datetime(feed_latest_published_at, entry_published_at)
            latest_published_at = _latest_datetime(latest_published_at, entry_published_at)

            if (
                scan_mode == SCAN_MODE_INCREMENTAL
                and previous_latest_published_at
                and entry_published_at
                and not _is_newer_than(entry_published_at, previous_latest_published_at)
            ):
                known_feed_entries += 1
                feed_known += 1
                cursor_reached = True
                logger.info(
                    "[google_alerts] Feed %s: cursor reached at published_at=%s",
                    feed_config.alert_name or feed_key,
                    entry_published_at,
                )
                break

            if entry_hash in known_hash_set or (entry_link and entry_link in known_link_set):
                known_feed_entries += 1
                feed_known += 1
                continue
            if entry_link and detection_exists_by_source_url(entry_link):
                skipped_existing += 1
                feed_skipped_existing += 1
                continue

            new_feed_entries += 1
            feed_new += 1
            events.append(
                _event_from_entry(
                    feed_config,
                    parsed_feed,
                    entry,
                    entry_hash=entry_hash,
                    scan_mode=scan_mode,
                )
            )

        if observed_hashes:
            feed_state_updates[feed_key] = (observed_hashes + known_hashes)[:200]
        if observed_links:
            feed_link_state_updates[feed_key] = (observed_links + known_links)[:200]
        if feed_latest_published_at and feed_latest_published_at != previous_latest_published_at:
            feed_published_updates[feed_key] = feed_latest_published_at

        feed_stats.append(
            {
                "feed": feed_config.alert_name or feed_key,
                "category": feed_config.category,
                "country": feed_config.country,
                "entries_seen": len(limited_entries),
                "known_entries": feed_known,
                "new_entries": feed_new,
                "skipped_existing": feed_skipped_existing,
                "previous_latest_published_at": previous_latest_published_at,
                "latest_published_at": feed_latest_published_at,
                "cursor_reached": cursor_reached,
                "errors": 0,
            }
        )

    stats = GoogleAlertsCollectionStats(
        feeds_loaded=len(feeds),
        valid_rss_urls=len(valid_feeds),
        feeds_processed=feeds_processed_count,
        skipped_missing_rss=skipped_missing_rss,
        skipped_placeholder_rss=skipped_placeholder_rss,
        skipped_invalid_rss_url=skipped_invalid_rss_url,
        skipped_invalid_structure=skipped_invalid_structure,
        entries_collected=known_feed_entries + new_feed_entries,
        known_feed_entries=known_feed_entries,
        new_feed_entries=new_feed_entries,
        feed_state_updates=feed_state_updates,
        feed_link_state_updates=feed_link_state_updates,
        feed_published_updates=feed_published_updates,
        errors=errors,
        config_error=str(diagnostics["parse_error"]),
        skipped_existing=skipped_existing,
        stopped_reason=stopped_reason,
        scan_mode=scan_mode,
        max_items_per_run=global_max_items,
        latest_published_at=latest_published_at,
        feed_stats=feed_stats,
    )
    logger.info(
        "[google_alerts] mode=%s collected=%s skipped_existing=%s known_feed_entries=%s new_feed_entries=%s",
        scan_mode,
        known_feed_entries + new_feed_entries,
        skipped_existing,
        known_feed_entries,
        new_feed_entries,
    )
    return GoogleAlertsCollectionResult(events=events, stats=stats)


def collect_google_alert_events(scan_mode: str | None = None) -> list[dict[str, Any]]:
    return collect_google_alert_events_with_stats(scan_mode).events
