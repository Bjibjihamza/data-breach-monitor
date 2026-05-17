# TODO Next Steps

## P0

- Fix dashboard metrics to show scan activity separately from lifetime totals.
- Add cards for `Total indexed`, `New in last scan`, `Duplicates skipped last scan`, `Last scan time`, and `New last 24h`.
- Wire dashboard to `/analytics/source-health`.
- Add an endpoint to read recent `collection_runs` summaries.
- Persist `skipped_noise`, `skipped_informational`, and source-specific counters in `collection_runs`.
- Add debug endpoint for GitHub query diagnostics:
  - total configured queries
  - first query index
  - queries selected this run
  - max queries per run
  - max results per query
  - max file fetches per run
- Add debug endpoint for Telegram source diagnostics:
  - configured channels
  - enabled channels
  - limit per channel
  - credential/session status without exposing secrets
- Remove or untrack runtime artifacts:
  - `celerybeat-schedule`
  - `data_breach_monitor.session`
  - `__pycache__/`
  - `test.py`
- Rotate credentials if `.env` was committed or shared.

## P1

- Add `collection_state` index.
- Add Telegram `last_seen_message_id` per channel.
- Change normal Telegram scan to fetch only messages newer than `last_seen_message_id`.
- Add Telegram backfill mode with explicit larger limits.
- Add GitHub query rotation using persisted `last_query_index`.
- Add GitHub per-category limits so early categories do not starve later categories.
- Add GitHub pagination controls.
- Add GitHub scan modes:
  - quick scan
  - full scan
  - global risk scan
- Improve Google Alerts per-feed diagnostics:
  - entries collected
  - indexed
  - duplicates skipped
  - errors
  - last successful fetch
- Decide whether Google Alerts dedup should collapse duplicate URLs across alert feeds.

## P2

- Remove or move unused placeholder collectors:
  - `app/collectors/gitlab_collector.py`
  - `app/collectors/hibp_collector.py`
- Decide whether `mock_paste_collector.py` remains a development-only collector or moves to `examples/`.
- Clean config consistency:
  - keep `config/organizations_watchlist.yml` documented as an opt-in affected-entity extension
  - remove `config/google_alerts_query_templates.yml` unless a generator uses it
  - remove unused Google Alerts env vars or implement them
- Add tests for:
  - GitHub query selection
  - Google Alerts hash stability
  - Telegram hash stability
  - duplicate summary counting
  - collection run persistence
- Convert source summary logs to structured logs with consistent keys.

## P3

- Add correlation layer across GitHub, Google Alerts, and Telegram.
- Add validation workflow for public breach claims.
- Add more sources only after current source state, dashboards, and run summaries are reliable.
- Consider bulk Elasticsearch writes if volume grows.
- Add operator documentation for scan modes and dashboard semantics.
