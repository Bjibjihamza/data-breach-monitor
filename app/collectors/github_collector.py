from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import requests

from app.collectors.github_content import fetch_repository_file_content
from app.collectors.scan_modes import (
    COLLECTOR_STATE_KEY,
    SCAN_MODE_BACKFILL,
    SCAN_MODE_INCREMENTAL,
    is_backfill,
    normalize_scan_mode,
)
from app.config import settings
from app.storage.elastic_client import (
    detection_exists_by_source_url,
    get_collection_state,
)
from app.watchlists.loader import github_search_specs


GITHUB_CODE_SEARCH_URL = "https://api.github.com/search/code"
GITHUB_PER_PAGE_LIMIT = 100
INCREMENTAL_KNOWN_RATIO_STOP = 0.8
INCREMENTAL_KNOWN_STREAK_STOP = 5
GITHUB_STATE_LIST_LIMIT = 5000
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GitHubCollectionStats:
    queries_loaded: int = 0
    queries_processed: int = 0
    files_fetched: int = 0
    content_fetch_failures: int = 0
    rate_limit_detected: bool = False
    query_window_start: int = 0
    query_window_end: int = 0
    next_last_query_index: int = 0
    pages_processed: int = 0
    results_seen: int = 0
    rotated: bool = True
    skipped_existing: int = 0
    stopped_reason: str = ""
    scan_mode: str = SCAN_MODE_INCREMENTAL
    max_items_per_run: int = 0
    last_cursor: str = ""
    seen_item_keys: list[str] = field(default_factory=list)
    known_item_keys: int = 0
    errors: int = 0
    query_stats: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class GitHubCollectionResult:
    events: list[dict[str, Any]]
    stats: GitHubCollectionStats
    seen_urls: list[str] = field(default_factory=list)


def _max_results_per_query() -> int:
    return max(1, settings.GITHUB_MAX_RESULTS_PER_QUERY)


def _max_queries_per_run() -> int:
    return max(1, settings.GITHUB_MAX_QUERIES_PER_RUN)


def _max_file_fetches_per_run() -> int:
    return max(1, settings.GITHUB_MAX_FILE_FETCHES_PER_RUN)


def _max_pages_per_query() -> int:
    return max(1, settings.GITHUB_MAX_PAGES_PER_QUERY)


def _global_max_items(scan_mode: str) -> int:
    if is_backfill(scan_mode):
        return max(1, settings.INITIAL_BACKFILL_MAX_ITEMS_PER_SOURCE)
    return max(1, settings.GITHUB_INCREMENTAL_MAX_ITEMS)


def _github_item_key(item: dict[str, Any]) -> str:
    repository = item.get("repository") or {}
    repo_name = str(repository.get("full_name") or "")
    file_path = str(item.get("path") or "")
    sha = str(item.get("sha") or "")
    html_url = str(item.get("html_url") or "")
    key = "|".join(part for part in (repo_name, file_path, sha) if part)
    return key or html_url


def _query_window(all_query_specs: list[Any], max_queries: int) -> tuple[list[Any], int, int, int]:
    total = len(all_query_specs)
    if total == 0:
        return [], 0, 0, 0
    state = get_collection_state("github", "global_query_rotation")
    last_query_index = int(state.get("last_query_index") or 0)
    start_zero = last_query_index % total
    window_size = min(max_queries, total)
    indices = [(start_zero + offset) % total for offset in range(window_size)]
    query_specs = [all_query_specs[index] for index in indices]
    start_display = indices[0] + 1
    end_display = indices[-1] + 1
    next_last_query_index = (start_zero + window_size) % total
    return query_specs, start_display, end_display, next_last_query_index


def _is_rate_limited(response: requests.Response) -> bool:
    if response.status_code in {403, 429} and response.headers.get("X-RateLimit-Remaining") == "0":
        return True

    try:
        message = str(response.json().get("message", "")).lower()
    except ValueError:
        message = ""

    return response.status_code in {403, 429} and "rate limit" in message


def _safe_rate_limit_message(response: requests.Response, query_index: int) -> str:
    reset_at = response.headers.get("X-RateLimit-Reset", "unknown")
    return f"GitHub rate limit reached for configured query #{query_index}; reset epoch={reset_at}. Skipping remaining GitHub pages."


def _safe_api_error_message(response: requests.Response) -> str:
    try:
        message = str(response.json().get("message", ""))
    except ValueError:
        message = response.text

    return (message or "no response body")[:200]


def _build_event(
    item: dict[str, Any],
    query: str,
    organization: str,
    risk_category: str,
    file_content: str,
    *,
    item_key: str,
    scan_mode: str,
) -> dict[str, Any]:
    repository = item.get("repository") or {}
    repo_name = repository.get("full_name", "unknown")
    file_path = item.get("path", "")
    html_url = item.get("html_url", "")
    title = f"{repo_name}:{file_path}"
    timestamp = datetime.now(timezone.utc).isoformat()

    return {
        "source": "github",
        "title": title,
        "url": html_url,
        "source_url": html_url,
        "organization": organization,
        "risk_category": risk_category,
        "raw_text": file_content,
        "timestamp": timestamp,
        "collected_at": timestamp,
        "scan_mode": scan_mode,
        "metadata": {
            "search_query_context": query,
            "organization": organization,
            "risk_category": risk_category,
            "repository": repo_name,
            "file_path": file_path,
            "item_key": item_key,
            "item_sha": item.get("sha") or "",
            "html_url": html_url,
            "scan_mode": scan_mode,
        },
    }


def _build_stats(
    *,
    all_query_specs: list[Any],
    queries_processed: int,
    file_fetches: int,
    skipped_content_fetch: int,
    rate_limit_detected: bool,
    window_start: int,
    window_end: int,
    next_last_query_index: int,
    pages_processed: int,
    results_seen: int,
    skipped_existing: int,
    stopped_reason: str,
    scan_mode: str,
    max_items: int,
    last_cursor: str,
    seen_item_keys: list[str],
    known_item_keys: int,
    errors: int,
    query_stats: list[dict[str, Any]] | None = None,
) -> GitHubCollectionStats:
    return GitHubCollectionStats(
        queries_loaded=len(all_query_specs),
        queries_processed=queries_processed,
        files_fetched=file_fetches,
        content_fetch_failures=skipped_content_fetch,
        rate_limit_detected=rate_limit_detected,
        query_window_start=window_start,
        query_window_end=window_end,
        next_last_query_index=next_last_query_index,
        pages_processed=pages_processed,
        results_seen=results_seen,
        skipped_existing=skipped_existing,
        stopped_reason=stopped_reason,
        scan_mode=scan_mode,
        max_items_per_run=max_items,
        last_cursor=last_cursor,
        seen_item_keys=seen_item_keys[:GITHUB_STATE_LIST_LIMIT],
        known_item_keys=known_item_keys,
        errors=errors,
        query_stats=query_stats or [],
    )


def collect_github_events_with_stats(scan_mode: str | None = None) -> GitHubCollectionResult:
    scan_mode = normalize_scan_mode(scan_mode)

    if not settings.GITHUB_TOKEN:
        logger.warning("GitHub token is not configured; skipping github collector.")
        return GitHubCollectionResult(
            events=[],
            stats=GitHubCollectionStats(scan_mode=scan_mode),
        )

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    events: list[dict[str, Any]] = []
    collector_state = get_collection_state("github", COLLECTOR_STATE_KEY)
    state_seen_items = collector_state.get("seen_item_keys")
    known_item_key_set = {
        str(item)
        for item in state_seen_items
        if item
    } if isinstance(state_seen_items, list) else set()
    previous_cursor = str(collector_state.get("last_cursor") or "")
    max_results = _max_results_per_query()
    max_queries = _max_queries_per_run()
    max_file_fetches = _max_file_fetches_per_run()
    max_pages_per_query = _max_pages_per_query()
    global_max_items = _global_max_items(scan_mode)
    per_page = min(max_results, GITHUB_PER_PAGE_LIMIT)
    max_pages = min(max_pages_per_query, math.ceil(max_results / per_page))
    all_query_specs = github_search_specs()
    query_specs, window_start, window_end, next_last_query_index = _query_window(all_query_specs, max_queries)
    if not query_specs:
        logger.warning("No GitHub search queries configured; skipping github collector.")
        return GitHubCollectionResult(
            events=[],
            stats=GitHubCollectionStats(scan_mode=scan_mode, max_items_per_run=global_max_items),
        )

    skipped_content_fetch = 0
    skipped_existing = 0
    file_fetches = 0
    queries_processed = 0
    pages_processed = 0
    results_seen = 0
    seen_urls: list[str] = []
    processed_item_keys: list[str] = []
    known_item_keys = 0
    collector_errors = 0
    incremental_known_streak = 0
    stopped_reason = ""
    query_stats: list[dict[str, Any]] = []

    logger.info(
        (
            "[github] mode=%s max_items_per_run=%s cursor=%s known_items=%s window=%s-%s/%s "
            "(max_queries_per_run=%s, max_results_per_query=%s, max_pages_per_query=%s, max_file_fetches_per_run=%s)."
        ),
        scan_mode,
        global_max_items,
        previous_cursor or "none",
        len(known_item_key_set),
        window_start,
        window_end,
        len(all_query_specs),
        max_queries,
        max_results,
        max_pages,
        max_file_fetches,
    )
    if len(all_query_specs) > max_queries:
        logger.info(
            "GitHub max query limit reached; executing first %s of %s configured query value(s).",
            max_queries,
            len(all_query_specs),
        )

    def _finalize(rate_limited: bool, reason: str) -> GitHubCollectionResult:
        stats = _build_stats(
            all_query_specs=all_query_specs,
            queries_processed=queries_processed,
            file_fetches=file_fetches,
            skipped_content_fetch=skipped_content_fetch,
            rate_limit_detected=rate_limited,
            window_start=window_start,
            window_end=window_end,
            next_last_query_index=next_last_query_index,
            pages_processed=pages_processed,
            results_seen=results_seen,
            skipped_existing=skipped_existing,
            stopped_reason=reason or stopped_reason,
            scan_mode=scan_mode,
            max_items=global_max_items,
            last_cursor=processed_item_keys[0] if processed_item_keys else previous_cursor,
            seen_item_keys=processed_item_keys,
            known_item_keys=known_item_keys,
            errors=collector_errors,
            query_stats=query_stats,
        )
        return GitHubCollectionResult(events=events, stats=stats, seen_urls=seen_urls)

    for query_index, spec in enumerate(query_specs, start=1):
        query = spec.query
        organization = spec.organization
        risk_category = spec.risk_category
        query_events = 0
        query_seen = 0
        query_skipped_existing = 0
        query_fetch_failures = 0
        query_pages = 0
        query_errors = 0
        query_stop_reason = ""
        queries_processed += 1

        if len(events) >= global_max_items:
            stopped_reason = "max_items_per_run_reached"
            logger.info(
                "[github] mode=%s stop reason=%s collected=%s limit=%s",
                scan_mode,
                stopped_reason,
                len(events),
                global_max_items,
            )
            break

        for page in range(1, max_pages + 1):
            remaining = max_results - query_events
            if remaining <= 0:
                break

            params = {
                "q": query,
                "per_page": min(per_page, remaining),
                "page": page,
                "sort": "indexed",
                "order": "desc",
            }
            try:
                response = requests.get(GITHUB_CODE_SEARCH_URL, headers=headers, params=params, timeout=20)
            except requests.RequestException as exc:
                query_errors += 1
                collector_errors += 1
                logger.warning(
                    "GitHub API request failed for configured query #%s page %s: %s",
                    query_index,
                    page,
                    exc.__class__.__name__,
                )
                break

            if _is_rate_limited(response):
                logger.warning(_safe_rate_limit_message(response, query_index))
                stopped_reason = "rate_limited"
                return _finalize(rate_limited=True, reason=stopped_reason)

            if response.status_code >= 400:
                query_errors += 1
                collector_errors += 1
                logger.warning(
                    "GitHub API error for configured query #%s page %s: HTTP %s: %s",
                    query_index,
                    page,
                    response.status_code,
                    _safe_api_error_message(response),
                )
                break

            try:
                payload = response.json()
            except ValueError:
                query_errors += 1
                collector_errors += 1
                logger.warning(
                    "GitHub API error for configured query #%s page %s: invalid JSON response.",
                    query_index,
                    page,
                )
                break

            items = payload.get("items", [])
            if not isinstance(items, list):
                query_errors += 1
                collector_errors += 1
                logger.warning("GitHub API error for configured query #%s page %s: items was not a list.", query_index, page)
                break
            pages_processed += 1
            query_pages += 1
            results_seen += len(items)
            query_seen += len(items)
            if not items:
                if page == 1:
                    logger.info("GitHub query #%s returned zero results.", query_index)
                break

            for item in items:
                if len(events) >= global_max_items:
                    stopped_reason = "max_items_per_run_reached"
                    logger.info(
                        "[github] mode=%s stop reason=%s collected=%s limit=%s",
                        scan_mode,
                        stopped_reason,
                        len(events),
                        global_max_items,
                    )
                    query_stop_reason = stopped_reason
                    query_stats.append(
                        {
                            "query_index": query_index,
                            "query": query,
                            "organization": organization,
                            "risk_category": risk_category,
                            "results_seen": query_seen,
                            "events_collected": query_events,
                            "skipped_existing": query_skipped_existing,
                            "content_fetch_failures": query_fetch_failures,
                            "pages_processed": query_pages,
                            "errors": query_errors,
                            "stopped_reason": query_stop_reason,
                        }
                    )
                    return _finalize(rate_limited=False, reason=stopped_reason)
                if query_events >= max_results:
                    logger.info(
                        "GitHub max results per query reached for query #%s: %s result(s).",
                        query_index,
                        max_results,
                    )
                    break
                if file_fetches >= max_file_fetches:
                    logger.info(
                        "GitHub max file fetch limit reached: %s fetch attempt(s). Stopping collector.",
                        max_file_fetches,
                    )
                    stopped_reason = "max_file_fetches_reached"
                    query_stop_reason = stopped_reason
                    query_stats.append(
                        {
                            "query_index": query_index,
                            "query": query,
                            "organization": organization,
                            "risk_category": risk_category,
                            "results_seen": query_seen,
                            "events_collected": query_events,
                            "skipped_existing": query_skipped_existing,
                            "content_fetch_failures": query_fetch_failures,
                            "pages_processed": query_pages,
                            "errors": query_errors,
                            "stopped_reason": query_stop_reason,
                        }
                    )
                    return _finalize(rate_limited=False, reason=stopped_reason)

                html_url = str(item.get("html_url") or "")
                item_key = _github_item_key(item)
                if html_url:
                    seen_urls.append(html_url)
                if scan_mode == SCAN_MODE_INCREMENTAL and item_key and item_key in known_item_key_set:
                    skipped_existing += 1
                    query_skipped_existing += 1
                    known_item_keys += 1
                    incremental_known_streak += 1
                    processed_item_keys.append(item_key)
                    logger.debug("[github] skip known item key=%s", item_key)
                    if incremental_known_streak >= INCREMENTAL_KNOWN_STREAK_STOP:
                        stopped_reason = "incremental_state_watermark_reached"
                        logger.info(
                            "[github] mode=%s stop reason=%s streak=%s cursor=%s",
                            scan_mode,
                            stopped_reason,
                            incremental_known_streak,
                            previous_cursor or "none",
                        )
                        return _finalize(rate_limited=False, reason=stopped_reason)
                    continue
                if html_url and detection_exists_by_source_url(html_url):
                    skipped_existing += 1
                    query_skipped_existing += 1
                    incremental_known_streak += 1
                    known_item_keys += 1
                    if item_key:
                        processed_item_keys.append(item_key)
                    logger.debug(
                        "[github] skip existing url=%s (mode=%s)", html_url, scan_mode,
                    )
                    if scan_mode == SCAN_MODE_INCREMENTAL and incremental_known_streak >= INCREMENTAL_KNOWN_STREAK_STOP:
                        stopped_reason = "incremental_known_streak"
                        logger.info(
                            "[github] mode=%s stop reason=%s streak=%s",
                            scan_mode,
                            stopped_reason,
                            incremental_known_streak,
                        )
                        return _finalize(rate_limited=False, reason=stopped_reason)
                    continue

                incremental_known_streak = 0
                file_fetches += 1
                file_content, fetch_error = fetch_repository_file_content(item, headers)
                if fetch_error:
                    if fetch_error == "http_403" or fetch_error == "http_429":
                        logger.warning(
                            "GitHub rate limit or forbidden while fetching file content; stopping collector."
                        )
                        stopped_reason = "rate_limited"
                        return _finalize(rate_limited=True, reason=stopped_reason)
                    skipped_content_fetch += 1
                    query_fetch_failures += 1
                    logger.info(
                        "Skipping GitHub result %s:%s - content fetch failed (%s)",
                        (item.get("repository") or {}).get("full_name", "unknown"),
                        item.get("path", ""),
                        fetch_error,
                    )
                    continue

                events.append(
                    _build_event(
                        item,
                        query,
                        organization,
                        risk_category,
                        file_content,
                        item_key=item_key,
                        scan_mode=scan_mode,
                    )
                )
                if item_key:
                    processed_item_keys.append(item_key)
                query_events += 1

            if len(items) < params["per_page"]:
                break

        query_stats.append(
            {
                "query_index": query_index,
                "query": query,
                "organization": organization,
                "risk_category": risk_category,
                "results_seen": query_seen,
                "events_collected": query_events,
                "skipped_existing": query_skipped_existing,
                "content_fetch_failures": query_fetch_failures,
                "pages_processed": query_pages,
                "errors": query_errors,
                "stopped_reason": query_stop_reason,
            }
        )

    if events:
        logger.info(
            "[github] mode=%s collected=%s skipped_existing=%s content_fetch_skips=%s fetch_attempts=%s",
            scan_mode,
            len(events),
            skipped_existing,
            skipped_content_fetch,
            file_fetches,
        )
    else:
        logger.info(
            "[github] mode=%s collected=0 skipped_existing=%s content_fetch_skips=%s fetch_attempts=%s",
            scan_mode,
            skipped_existing,
            skipped_content_fetch,
            file_fetches,
        )

    return _finalize(rate_limited=False, reason=stopped_reason)


def collect_github_events(scan_mode: str | None = None) -> list[dict[str, Any]]:
    return collect_github_events_with_stats(scan_mode).events
