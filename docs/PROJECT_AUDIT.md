# Data Breach Monitor Project Audit

## Executive Summary

Seeing `292` total detections on every refresh can be normal for this codebase, but the dashboard makes it look like nothing happened. The visible total is the lifetime count in Elasticsearch, not the number of new documents from the latest scan.

The current collectors mostly re-read a fixed window:

- GitHub executes the first 20 configured queries every run, fetches up to 50 files globally, and has no cursor or query rotation.
- Google Alerts reads the first 20 valid RSS feeds and up to 25 entries per feed. The configured file has 18 valid feeds, so repeated RSS stability can naturally produce the same set.
- Telegram reads the latest messages from configured public channels. The only configured channel has `limit_per_run: 10`, so the observed `10` is expected unless that channel posts new messages.

Deduplication is working in the sense that existing hashes are skipped before indexing. The misleading part is that the dashboard primarily shows total indexed detections and source totals, not latest-run activity such as `indexed=0`, `duplicates_skipped=275`, or `collected=275`.

## Current Observed Behavior

Observed total:

- Total detections: `292`
- Google Alerts: `275`
- Telegram: `10`
- GitHub: `7`

This distribution is plausible with the current implementation:

- Google Alerts has 18 configured valid feeds. RSS feeds commonly return a stable latest window of roughly 10-20 entries. `275` is consistent with 18 feeds times about 15 entries, minus overlap or feed variance.
- Telegram has one enabled channel, `CVEDetector`, configured for `limit_per_run: 10`.
- GitHub has 116 configured query specs, but only the first 20 are executed per scan and file fetches stop after 50 attempts. Only 7 detections passing validation is plausible.

## Why Total Stays 292

The total stays fixed because the indexed corpus is stable. Each scan can still be running and collecting data, but repeated items are skipped by hash before indexing.

The dashboard currently emphasizes:

- `total_detections` from `/analytics/summary`
- source totals from Elasticsearch aggregations
- latest 50 detections from `/detections?limit=50`

It does not prominently show:

- new detections in the last scan
- duplicates skipped in the last scan
- collected items in the last scan
- scan run history from `collection_runs`
- new detections in the last 24 hours

So a successful scan that collects 275 Google Alerts entries and indexes 0 new documents still looks like no-op behavior.

## Source-by-Source Findings

### GitHub

Collector:

- `app/collectors/github_collector.py`
- task path: `app.tasks.scan_github_task`
- processing path: `_process_events("github", collect_github_events)`
- query builder: `app/watchlists/loader.py::github_search_specs`

Configs used:

- `app/watchlists/global_risks.yml`
- `WATCHLISTS_GLOBAL_RISKS_PATH`
- `WATCHLISTS_ORGANIZATIONS_DIR`, defaulting to `app/watchlists/organizations`
- optional organization profiles only when `ORGANIZATION_WATCHLISTS_ENABLED=true`
- `GITHUB_SEARCH_QUERIES`
- `GITHUB_MAX_RESULTS_PER_QUERY`
- `GITHUB_MAX_QUERIES_PER_RUN`
- `GITHUB_MAX_FILE_FETCHES_PER_RUN`
- `GITHUB_MAX_CONTENT_BYTES`
- `GITHUB_CONTENT_FETCH_TIMEOUT`

Configs not used by GitHub:

- `config/organizations_watchlist.yml`

Limits:

- `GITHUB_MAX_QUERIES_PER_RUN=20`
- `GITHUB_MAX_RESULTS_PER_QUERY=30`
- `GITHUB_MAX_FILE_FETCHES_PER_RUN=50`
- GitHub API per-page hard cap: 100

Observed local config facts:

- `global_risks.yml` currently produces 116 GitHub search specs.
- Only the first 20 are executed each run.
- The first 20 are deterministic and cover early categories: `env_files` and `database_credentials`.
- The configured organization watchlist under `config/organizations_watchlist.yml` is not part of GitHub query generation.

Behavior:

- The collector always starts from query 1.
- Query order is fixed.
- There is no query rotation.
- There is no persisted cursor.
- There is no created/updated date window in queries.
- Pagination exists structurally, but with the current default `GITHUB_MAX_RESULTS_PER_QUERY=30`, `per_page=30` and `max_pages=1`, so each query effectively only scans page 1.
- File content fetches are globally capped at 50. Once reached, the collector returns immediately.
- Rate limit detection exists for HTTP 403/429 and `X-RateLimit-Remaining: 0`, but rate-limit state is not persisted and dashboard diagnostics do not show it.
- Ignored findings are logged with reason, validated secret count, and placeholder count, but there is no searchable record of ignored items.

Answer:

- Is GitHub collecting new data or re-reading same items? Mostly re-reading the same first-page results from the same first 20 queries unless GitHub search ranking changes.
- Is `7` expected? Yes, given aggressive validation, deterministic first 20 queries, and 50 file fetch cap.
- What controls are missing? Query rotation, state, cursor, date windows, scan modes, per-category quotas, richer ignored-result analytics.
- What should improve? Add rotation, pagination controls, date-scoped searches, separate quick/full/org/global modes, and store skipped/noise/duplicate analytics per query.

### Google Alerts

Collector:

- `app/collectors/google_alerts_collector.py`
- task path: `app.tasks.run_google_alerts_scan`
- normalization path: `app/processing/google_alerts.py`

Config used:

- hardcoded path `config/google_alerts_feeds.yml`
- `GOOGLE_ALERTS_MAX_ENTRIES_PER_FEED`
- `GOOGLE_ALERTS_MAX_FEEDS_PER_RUN`

Config not actually used:

- `GOOGLE_ALERTS_CONFIG_PATH`
- `GOOGLE_ALERTS_RSS_URL`
- `GOOGLE_ALERTS_ENABLED`
- `GOOGLE_ALERTS_SCAN_INTERVAL_HOURS`
- `config/google_alerts_query_templates.yml`

Limits:

- `GOOGLE_ALERTS_MAX_FEEDS_PER_RUN=20`
- `GOOGLE_ALERTS_MAX_ENTRIES_PER_FEED=25`
- current config has 18 valid RSS feeds, so all feeds are processed.

Behavior:

- All valid feeds are loaded from `config/google_alerts_feeds.yml`.
- Each feed fetches RSS over HTTP and processes the first `max_entries_per_feed` entries.
- No per-feed cursor exists.
- No last-seen state exists.
- The same stable RSS entries are re-collected each run until Google emits new feed items.
- Dedup is by `source|alert_name|source_url|title`.
- Old indexed articles remain visible because dashboard totals are lifetime totals unless the user filters by date.
- `collection_runs` summaries are saved, but the dashboard does not make them central.

Answer:

- Is Google Alerts collecting new data or re-reading same items? It re-reads the latest RSS windows and indexes only previously unseen entries.
- Is `275` expected? Yes. It is consistent with 18 feeds times a stable feed window.
- What controls are missing? Per-feed diagnostics in the dashboard, last-seen tracking, latest-run cards, and clearer duplicate metrics.
- What should improve? Keep RSS behavior, but show `collected`, `indexed`, and `duplicates_skipped` per feed and per run.

### Telegram

Collector:

- `app/collectors/telegram_collector.py`
- task path: `app.tasks.scan_telegram_channels`
- normalization path: `app/processing/telegram.py`

Config used:

- `config/telegram_sources.yml`
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_SESSION_NAME`
- `TELEGRAM_LIMIT_PER_CHANNEL` when YAML omits `limit_per_run`

Limits:

- YAML overrides env: `CVEDetector` has `limit_per_run: 10`.
- Only one channel is enabled.

Behavior:

- Fetches latest messages with `client.get_messages(username, limit=channel.limit_per_run)`.
- Does not persist `last_seen_message_id`.
- Does not request messages newer than a saved ID.
- Does not support backfill mode separately from regular scan.
- Dedup is by `telegram:{channel_username}:{message_id}`.

Answer:

- Is Telegram collecting new data or re-reading same items? It re-reads the latest 10 channel messages each scan.
- Is `10` expected? Yes, because the configured channel limit is 10.
- What controls are missing? Per-channel state, last seen message ID, backfill mode, channel-level stats, and configurable regular-vs-backfill limits.
- What should improve? Store last seen per channel and fetch only newer messages during normal scans.

## GitHub Controls Needed

GitHub needs the largest refactor because the current loop is deterministic and shallow.

Required controls:

- Query rotation across the 116 specs instead of always `all_query_specs[:20]`.
- Per-category limits so early categories do not starve later categories.
- Persistent `collection_state` for `last_query_index`.
- Optional pagination beyond page 1.
- Date-scoped queries using `indexed`, `created`, or `pushed` search qualifiers where appropriate.
- Separate scan modes:
  - quick scan: small rotating window
  - full scan: all configured queries with controlled pagination
  - global risk scan: global exposure queries with controlled pagination
  - global risk scan: `global_risks.yml` only
- Per-query accounting:
  - collected
  - content_fetch_failed
  - skipped_noise
  - skipped_duplicates
  - indexed
  - rate_limited

The existing ignored-result log is useful, but it is not enough for operational diagnosis because it is only in worker logs and not aggregated.

## Google Alerts Behavior

Google Alerts returning the same total is likely normal. RSS feeds are stable latest-item windows. If Google has not published new alerts or the feed entries already exist in Elasticsearch, dedup skips them.

Current behavior is acceptable for a simple RSS collector, but the UI needs better semantics:

- total indexed
- new in last run
- duplicates skipped in last run
- latest run time
- new in last 24h
- per-feed collected/indexed/duplicate/error counts

## Telegram Behavior

Telegram returning 10 total is expected with the current `CVEDetector` config. The collector asks for the latest 10 messages each time, not messages since the last scan.

Normal mode should be stateful:

```json
{
  "source": "telegram",
  "key": "CVEDetector",
  "last_seen_message_id": 12345,
  "updated_at": "2026-05-16T00:00:00Z"
}
```

Backfill should be an explicit separate mode with a larger limit.

## Deduplication Analysis

GitHub:

- hash implemented in `app/processing/deduplicator.py`
- input: `source|source_url|redacted_text`
- stable for identical file URL and redacted content
- can create a new detection if file content changes
- can miss semantic updates if source URL and redacted text stay identical
- should be changed to include source, repository, path, blob URL or commit/file URL, and evidence type

Google Alerts:

- hash implemented in `app/processing/google_alerts.py`
- input: `source|alert_name|source_url|title`
- appropriate for RSS entry dedup
- alert name in the hash means the same URL appearing in multiple alerts can index more than once
- should decide whether cross-feed duplicates should collapse by canonical URL

Telegram:

- hash implemented in `app/processing/telegram.py`
- input: `telegram:{channel_username}:{message_id}`
- correct and stable for public channel messages

Dedup check:

- `detection_exists()` checks Elasticsearch by document ID before indexing.
- duplicates are counted in task summaries.
- duplicate counts are not strongly surfaced in the dashboard.

## Dashboard Semantics Problem

Dashboard path:

- HTML: `app/templates/dashboard.html`
- `/analytics/summary` returns lifetime totals and aggregations.
- `/detections?limit=50` returns latest indexed documents.
- `/analytics/source-health` exists but the dashboard does not appear to consume it.

The current KPI cards show:

- Total detections
- GitHub
- Google Alerts
- Telegram
- severity/status counts

They do not show the scan outcome. This is the main reason repeated successful scans look broken.

Recommended cards:

- Total indexed
- New in last scan
- Duplicates skipped last scan
- Last scan time
- New last 24h
- Source totals
- Source health

Also add source-specific last run panels showing `collected`, `indexed`, `duplicates_skipped`, `skipped_noise`, `errors`, and `message`.

## Scan Summary Audit

Implemented:

- `collection_runs` index exists in `app/storage/elastic_client.py`.
- `save_scan_run_summary()` stores one document per completed or failed scan.
- Redis scan status exists in `app/storage/scan_status.py`.
- source health can read latest run per source.

Current summary fields:

- `source`
- `started_at`
- `ended_at`
- `status`
- `collected`
- `indexed`
- `duplicates_skipped`
- `errors`
- `message`

Missing or weak:

- `skipped_noise` is returned by generic GitHub processing but not stored in `collection_runs`.
- `skipped_informational` is not stored.
- Google-specific feed stats are returned in task results but not persisted in the run document.
- Telegram channel-level stats are not persisted.
- There is no endpoint to list recent `collection_runs` directly.
- Dashboard does not use latest scan summaries as first-class UI data.

Recommended additions:

- Add `GET /analytics/collection-runs?source=&limit=`.
- Store all source-specific counters in `collection_runs`.
- Add optional nested `details` object for feed/channel/query diagnostics.

## File Structure Cleanup

Keep:

- `app/collectors/github_collector.py`
- `app/collectors/github_content.py`
- `app/collectors/google_alerts_collector.py`
- `app/collectors/telegram_collector.py`
- `app/processing/*`
- `app/storage/elastic_client.py`
- `app/storage/scan_status.py`
- `app/watchlists/global_risks.yml`
- `config/google_alerts_feeds.yml`
- `config/telegram_sources.yml`
- `config/detection_policy.yml`
- `docs/SCOPE.md`

Refactor:

- `app/tasks.py`: split source-specific scan processors after metrics are stabilized.
- `app/templates/dashboard.html`: separate API data loading from rendering, and add scan summary panels.
- `app/watchlists/loader.py`: either support `config/organizations_watchlist.yml` or remove that config file.

Remove or move:

- `app/collectors/gitlab_collector.py`: placeholder only. Move to docs/examples or remove until implemented.
- `app/collectors/hibp_collector.py`: placeholder only. Move to docs/examples or remove until implemented.
- `app/collectors/mock_paste_collector.py`: keep only for development demo if explicitly needed; otherwise move to `examples/`.
- `test.py`: appears to be an Elasticsearch/detection dump containing sensitive-looking sample values. Remove from repo.
- `celerybeat-schedule`: runtime artifact. Do not commit.
- `data_breach_monitor.session`: Telegram session artifact. Do not commit.
- `__pycache__/`: generated Python bytecode. Do not commit.

`.gitignore` already includes `.env`, `*.session`, `celerybeat-schedule`, and `__pycache__/`. If these files are already tracked, remove them from Git tracking without deleting local runtime copies.

## Config Cleanup

Used configs:

- `config/google_alerts_feeds.yml`: used by Google Alerts collector.
- `config/telegram_sources.yml`: used by Telegram collector.
- `config/detection_policy.yml`: used by detection scoring/noise logic.
- `app/watchlists/global_risks.yml`: used by GitHub query generation.

Unused or misleading configs:

- `config/organizations_watchlist.yml`: not loaded by current code.
- `config/google_alerts_query_templates.yml`: not loaded by current code.

Duplicate concepts:

- `config/organizations_watchlist.yml` and `app/watchlists/organizations/` represent two different organization profile locations. The code only uses the latter.
- `GOOGLE_ALERTS_CONFIG_PATH` suggests configurable feed path, but collector uses the hardcoded project path.
- `GOOGLE_ALERTS_SCAN_INTERVAL_HOURS` exists in `.env`, but Celery uses `GOOGLE_ALERTS_INTERVAL_MINUTES`.

Recommendation:

- Either migrate `config/organizations_watchlist.yml` into `app/watchlists/organizations/*.yml`, or update `load_organizations()` to parse it.
- Remove `google_alerts_query_templates.yml` unless you add a generator that creates feed definitions from organization/query templates.
- Align env var names with code and README.

## Environment Variables Audit

| Variable | Used | Default | Location | Risk if missing |
|---|---:|---|---|---|
| `APP_ENV` | yes | `development` | `app/config.py`, admin endpoint | Dev-only admin behavior may be wrong |
| `ELASTICSEARCH_URL` | yes | `http://localhost:9200` | storage | scans and dashboard fail without ES |
| `REDIS_URL` | yes | `redis://localhost:6379/0` | Celery, scan status | task queue/status fail |
| `GITHUB_TOKEN` | yes | empty | GitHub collector, source health | GitHub scans skip if missing |
| `GITHUB_SEARCH_QUERIES` | yes | empty | watchlist loader | optional extra queries |
| `GITHUB_MAX_RESULTS_PER_QUERY` | yes | `30` | GitHub collector | too low makes pagination shallow |
| `GITHUB_MAX_QUERIES_PER_RUN` | yes | `20` | GitHub collector | only first N deterministic queries run |
| `GITHUB_MAX_FILE_FETCHES_PER_RUN` | yes | `50` | GitHub collector | collector stops globally after limit |
| `GITHUB_MAX_CONTENT_BYTES` | yes | `524288` | GitHub content fetch | large files truncated/skipped |
| `GITHUB_CONTENT_FETCH_TIMEOUT` | yes | `15` | GitHub content fetch | slow fetches fail |
| `GOOGLE_ALERTS_MAX_ENTRIES_PER_FEED` | yes | `25` | Google Alerts collector | controls latest RSS window |
| `GOOGLE_ALERTS_MAX_FEEDS_PER_RUN` | yes | `20` | Google Alerts collector | controls feed subset |
| `TELEGRAM_API_ID` | yes | `0` | Telegram collector | Telegram scans fail if missing |
| `TELEGRAM_API_HASH` | yes | empty | Telegram collector | Telegram scans fail if missing |
| `TELEGRAM_SESSION_NAME` | yes | `data_breach_monitor` | Telegram collector | controls session file path |
| `TELEGRAM_LIMIT_PER_CHANNEL` | yes | `20` | Telegram config loader | overridden by YAML `limit_per_run` |
| `COLLECTION_INTERVAL_MINUTES` | yes | `30` | Celery schedule fallback | shared default cadence |
| `GOOGLE_ALERTS_INTERVAL_MINUTES` | yes | collection interval | Celery beat | Google cadence |
| `TELEGRAM_INTERVAL_MINUTES` | yes | collection interval | Celery beat | Telegram cadence |
| `GITHUB_INTERVAL_MINUTES` | yes | `60` | Celery beat | GitHub cadence |
| `TELEGRAM_BOT_TOKEN` | yes | empty | alert placeholder | Telegram alerting disabled |
| `TELEGRAM_CHAT_ID` | yes | empty | alert placeholder | Telegram alerting disabled |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_EMAIL_TO` | partially | empty | config only / alert placeholder | email alerting currently placeholder |
| `WATCHLISTS_ORGANIZATIONS_DIR` | yes | `app/watchlists/organizations` | watchlist loader | config file under `config/` is ignored |
| `WATCHLISTS_GLOBAL_RISKS_PATH` | yes | `app/watchlists/global_risks.yml` | watchlist loader | GitHub query list missing if wrong |
| `GOOGLE_ALERTS_RSS_URL` | no | empty | config only | misleading legacy setting |
| `GOOGLE_ALERTS_CONFIG_PATH` | no | none | `.env` only | misleading; collector ignores it |
| `GOOGLE_ALERTS_ENABLED` | no | none | `.env` only | misleading; source health uses valid feeds |
| `GOOGLE_ALERTS_SCAN_INTERVAL_HOURS` | no | none | `.env` only | misleading; minutes var is used |

Security note: `.env` currently contains real-looking GitHub and Telegram credentials. Rotate them if they were ever committed or shared.

## Logging Audit

Good:

- collectors log config loaded and source counts.
- GitHub logs query limit and file fetch failures.
- processing logs duplicate skips and ignored GitHub results with reason.
- end-of-scan summaries log collected/indexed/duplicates/errors.

Missing:

- per-query GitHub summary.
- per-feed Google Alerts summary.
- per-channel Telegram summary.
- persistent ignored-result analytics.
- visible dashboard log of rate limit events.
- structured logs with consistent keys across collectors.

Required scan log shape:

```json
{
  "source": "github",
  "run_id": "...",
  "config_loaded": true,
  "configured_items": 116,
  "processed_items": 20,
  "collected": 50,
  "indexed": 0,
  "duplicates_skipped": 43,
  "skipped_noise": 7,
  "errors": 0,
  "rate_limited": false
}
```

## Rate Limits and Controls

GitHub:

- Basic rate-limit detection exists.
- No backoff state, no cooldown state, no dashboard health warning.
- Scanning too frequently can waste API budget because scans repeat the same queries.

Google Alerts:

- RSS fetches are simple HTTP requests with timeout.
- Stable repeated RSS windows are normal.
- No conditional requests, ETag, Last-Modified, or per-feed cooldown.

Telegram:

- Uses Telethon and fetches latest messages.
- No flood-wait handling beyond generic RPC error handling.
- No per-channel state.

Elasticsearch:

- Indexes one document at a time.
- Duplicate check performs an ES exists call per detection.
- Current volume is small, but bulk operations would be better if volume grows.

Recommended controls:

- per-source scan intervals
- per-run max limits
- backoff/cooldown after API errors
- GitHub query rotation before increasing frequency
- avoid re-index attempts for old Google RSS entries by keeping per-feed last seen state

## State Management Audit

Current persisted state:

- indexed detections in `breach_signals`
- run history in `collection_runs`
- ephemeral scan status in Redis with 14-day TTL

Missing persisted collection state:

- GitHub last query position
- Telegram last seen message ID
- Google Alerts last seen hashes or latest scan markers per feed

Recommended `collection_state` index:

```json
{
  "source": "telegram",
  "key": "CVEDetector",
  "last_seen_message_id": 12345,
  "updated_at": "2026-05-16T00:00:00Z"
}
```

```json
{
  "source": "github",
  "key": "global_query_rotation",
  "last_query_index": 20,
  "updated_at": "2026-05-16T00:00:00Z"
}
```

```json
{
  "source": "google_alerts",
  "key": "Global cyber incidents monitoring",
  "last_seen_entry_hashes": ["..."],
  "updated_at": "2026-05-16T00:00:00Z"
}
```

## Recommended Refactor Roadmap

### Quick Fixes

1. Update dashboard KPIs to distinguish lifetime totals from latest-run metrics.
2. Add `/analytics/collection-runs` endpoint.
3. Show source health cards from `/analytics/source-health`.
4. Persist `skipped_noise`, `skipped_informational`, and source-specific counters in `collection_runs`.
5. Add debug endpoints for GitHub query config and Telegram source config.
6. Remove tracked runtime artifacts and rotate exposed credentials.

### Medium-Term Improvements

1. Add `collection_state` index.
2. Implement Telegram `last_seen_message_id`.
3. Implement GitHub query rotation.
4. Add GitHub pagination and per-category quotas.
5. Add Google Alerts per-feed diagnostics and state.
6. Add tests for dedup hashes and source summaries.

### Later Improvements

1. Add correlation layer across sources.
2. Add validation layer for external breach claims.
3. Add more sources only after current source semantics are clean.

## Files to Delete or Ignore

Delete or untrack:

- `test.py`
- `celerybeat-schedule`
- `data_breach_monitor.session`
- all `__pycache__/` directories

Move or remove placeholders:

- `app/collectors/gitlab_collector.py`
- `app/collectors/hibp_collector.py`

Keep only for demo/dev:

- `app/collectors/mock_paste_collector.py`

Already ignored:

- `.env`
- `*.session`
- `celerybeat-schedule`
- `__pycache__/`

## Files to Keep

- `docs/SCOPE.md`: keep. It clearly states the defensive OSINT scope and should remain.
- `app/watchlists/global_risks.yml`: keep, but add rotation controls.
- `config/google_alerts_feeds.yml`: keep.
- `config/telegram_sources.yml`: keep.
- `config/detection_policy.yml`: keep.

## Final Target Architecture

Target flow:

1. Source config is loaded and validated.
2. Source state is read from `collection_state`.
3. Collector fetches only the intended window for the selected scan mode.
4. Processor normalizes, scores, deduplicates, and indexes.
5. Every skipped and indexed outcome is counted.
6. `collection_runs` stores a complete run summary.
7. `collection_state` is updated only after successful collection.
8. Dashboard shows both lifetime totals and latest-run deltas.

The immediate goal is not more sources. The immediate goal is to make the existing three sources explainable and operationally trustworthy.
