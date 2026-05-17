# External Data Exposure & Breach Monitoring Platform

A defensive **External Data Exposure & Breach Monitoring Platform** for detecting publicly exposed sensitive data across authorized public OSINT sources.

This is **not** a generic vulnerability scanner. It does not perform port scanning, CVE exploitation, web app vulnerability scanning, pentesting automation, malware analysis, or any offensive security actions.

## What It Monitors

The platform focuses on **data breach and data exposure** signals, including:

- Leaked credentials, API keys, tokens, and cloud keys
- Database URIs and password assignments
- Exposed `.env` files and confidential keywords
- Global public exposure patterns (`.env`, API keys, DB URIs, private keys)
- Public code/config leaks and breach indicators at global scale
- Optional affected-entity correlation when explicitly enabled

**GitHub** collects technical exposure evidence. **Google Alerts** collects public breach/news signals. **Telegram** collects public-channel OSINT/CVE intelligence signals. **`mock_paste`** is for local testing and demo only.

## Safety Scope

Defensive OSINT monitoring and academic demonstration only. The MVP does not collect, store, or exploit real stolen credentials.

It does not scrape dark web forums, private forums, login-protected sources, private Telegram channels, or stolen databases. Telegram monitoring is limited to configured public channels.

GitHub monitoring uses the public GitHub Search API and stores only **redacted** detection records in the `breach_signals` Elasticsearch index.

## Architecture

```
frontend/
  src/
    api/        # Centralized relative-path API clients
    hooks/      # Independent endpoint loading and refresh hooks
    layout/     # Sidebar/topbar dashboard shell
    pages/      # Route-level dashboard pages
    components/ # Reusable cards, tables, badges, modal, charts
```

```
app/
├── watchlists/          # Risk-first watchlist loader and YAML profiles
│   ├── global_risks.yml # Global public exposure queries (primary)
│   └── organizations/ # Optional organization correlation profiles
├── organizations/       # Re-exports watchlist models
├── collectors/          # Source collectors (GitHub, mock_paste, …)
├── processing/          # Clean, detect, score, redact, normalize
├── storage/             # Elasticsearch and SQLite clients
├── alerts/              # Alert channel placeholders
└── main.py              # FastAPI entrypoint
```

- **FastAPI** exposes health and manual scan endpoints.
- **Celery** runs background scan jobs; **Celery Beat** schedules GitHub, Google Alerts, and Telegram scans.
- **Redis** is the Celery broker and result backend.
- **Elasticsearch** stores redacted detections in `breach_signals`.
- **Kibana** visualizes Elasticsearch data.

See [docs/SCOPE.md](docs/SCOPE.md) for full in-scope / out-of-scope boundaries.

## Services

- `api`: FastAPI on port `8000`
- `worker`: Celery worker
- `beat`: Celery Beat scheduler
- `redis`: broker on port `6379`
- `elasticsearch`: development cluster on port `9200`
- `kibana`: UI on port `5601`

## Run Locally

```bash
cp .env.example .env
cp config/google_alerts_feeds.example.yml config/google_alerts_feeds.yml
docker compose up --build
```

Keep `.env` and `config/google_alerts_feeds.yml` private. They are ignored by Git because they can contain tokens, SMTP credentials, Telegram credentials, and personal Google Alerts RSS feed identifiers.

Useful URLs:

- FastAPI: http://localhost:8000
- **Frontend dev UI**: http://localhost:5173/dashboard
- Kibana: http://localhost:5601
- Elasticsearch: http://localhost:9200

### React dashboard development

The dashboard frontend is a Vite React app under `frontend/`. During development, run FastAPI on port `8000` and Vite on port `5173`; Vite proxies API requests to FastAPI.

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173/dashboard
```

### React dashboard production build

FastAPI serves the built React app from `frontend/dist` at `/dashboard` and built assets from `/dashboard/assets`.

```bash
cd frontend
npm install
npm run build
```

Then start the FastAPI stack and open:

```text
http://localhost:8000/dashboard
```

If `frontend/dist/index.html` is missing, FastAPI shows a minimal fallback page with build instructions instead of the old monolithic dashboard.

Collection intervals are controlled by optional environment variables:

```env
COLLECTION_INTERVAL_MINUTES=30
GOOGLE_ALERTS_INTERVAL_MINUTES=30
TELEGRAM_INTERVAL_MINUTES=30
GITHUB_INTERVAL_MINUTES=60
```

Celery Beat starts these scheduled scans after `docker compose up --build`. Google Alerts and Telegram run every 30 minutes by default; GitHub runs every 60 minutes by default to reduce rate-limit pressure. Each run indexes only new documents and skips existing `detection_hash` values.

Collection volume limits are also configurable:

```env
GITHUB_MAX_RESULTS_PER_QUERY=30
GITHUB_MAX_QUERIES_PER_RUN=20
GITHUB_MAX_FILE_FETCHES_PER_RUN=50

GOOGLE_ALERTS_MAX_ENTRIES_PER_FEED=25
GOOGLE_ALERTS_MAX_FEEDS_PER_RUN=20

TELEGRAM_LIMIT_PER_CHANNEL=20
```

`config/telegram_sources.yml` can still set `limit_per_run` per channel; that YAML value overrides `TELEGRAM_LIMIT_PER_CHANNEL`.

Trigger a GitHub public scan:

```bash
curl -X POST http://localhost:8000/scan/github
```

Trigger a Google Alerts public-news scan:

```bash
curl -X POST http://localhost:8000/scan/google-alerts
```

Trigger a Telegram public-channel OSINT scan:

```bash
curl -X POST http://localhost:8000/scan/telegram
```

Mock paste scan (local test/demo only):

```bash
curl -X POST http://localhost:8000/scan/mock
```

## Monitoring Model

Monitoring is **global-first**. GitHub scans are driven by the global public exposure categories and queries in `app/watchlists/global_risks.yml`; organization watchlists are not required for the MVP.

The current objective is to detect public exposure patterns at scale, including `.env` files, database credentials, API keys, cloud keys, GitHub tokens, JWT secrets, private keys, password assignments, Docker/Kubernetes secrets, application config leaks, public code leaks, CVE/exploit/PoC references, and generic breach/exposure indicators.

Optional organization watchlists can be enabled later for affected-entity tagging and correlation, but GitHub scanning does not depend on them.

## Telegram Public Channels

Telegram ingestion monitors only public channels listed in `config/telegram_sources.yml`. Telegram messages are stored as OSINT signals that require validation; they are not treated as confirmed breach evidence.

Configure Telegram:

1. Create API credentials at https://my.telegram.org.
2. Add these values to `.env`:

```env
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_SESSION_NAME=data_breach_monitor
```

3. Add public channels to `config/telegram_sources.yml`:

```yaml
channels:
  - name: "CVEDetector"
    username: "CVEDetector"
    url: "https://t.me/CVEDetector"
    category: "cve_intelligence"
    source_type: "telegram_public_channel"
    limit_per_run: 10
    enabled: true
```

4. Run one interactive login to create the Telethon session file. For Docker, run this from the project root after adding credentials:

```bash
docker compose run --rm api python -c "from telethon.sync import TelegramClient; from app.config import settings; TelegramClient(settings.TELEGRAM_SESSION_NAME, settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH).start()"
```

5. Start the stack and trigger a scan:

```bash
docker compose up --build
curl -X POST http://localhost:8000/scan/telegram
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/scan/telegram
```

Open the dashboard:

http://localhost:8000/dashboard

### Global risk profiles

`app/watchlists/global_risks.yml` defines categories such as `env_files`, `database_credentials`, `api_keys`, `cloud_keys`, `jwt_tokens`, `private_keys`, `docker_secrets`, and `framework_configs`. Each category includes `name`, `severity_hint`, and GitHub `queries`.

Override the file path:

```env
WATCHLISTS_GLOBAL_RISKS_PATH=/path/to/global_risks.yml
```

## Organization Watchlists (optional extension)

Organization watchlists are disabled by default. They are not required for GitHub scanning and are not part of the default MVP collection strategy.

To enable optional affected-entity correlation and organization-derived extra queries:

```env
ORGANIZATION_WATCHLISTS_ENABLED=true
```

When enabled, organization watchlists can be configured in either place:

- `config/organizations_watchlist.yml` with a top-level `organizations:` list
- one YAML file per organization under `app/watchlists/organizations/`

The config file path can be overridden with:

```env
ORGANIZATION_WATCHLISTS_ENABLED=true
WATCHLISTS_ORGANIZATIONS_FILE=/path/to/organizations_watchlist.yml
WATCHLISTS_ORGANIZATIONS_DIR=/path/to/organizations
```

Example (`app/watchlists/organizations/example_org.yml`):

```yaml
name: Example Organization
category: education
country: MA
domains:
  - example.com
  - example.org
email_patterns:
  - "@example.com"
keywords:
  - Example Brand
  - internal-project-name
github_queries:
  - '"example.com" ".env"'
  - '"example.com" "DB_PASSWORD"'
  - '"example.com" "API_KEY"'
  - '"example.com" "SECRET_KEY"'
  - '"example.com" "token"'
source_settings:
  github:
    enabled: true
```

Optional fields: `brand_names`, `internal_project_names`, `source_settings`.

The GitHub collector builds search queries from:

1. Global risk profiles (`global_risks.yml`)
2. Optional `GITHUB_SEARCH_QUERIES` environment variable
3. Organization profiles only when `ORGANIZATION_WATCHLISTS_ENABLED=true`

For global risk queries, `organization` is empty/unknown unless an optional correlation layer later tags an affected entity. `risk_category` is set from the global profile, such as `env_files`, `database_credentials`, `api_keys`, or `private_keys`. File content is always fetched when possible; only detections with exposure evidence in the actual file content are stored.

`config/organizations_watchlist.yml` is kept as an optional future/extension config. If it exists while `ORGANIZATION_WATCHLISTS_ENABLED=false`, it is ignored safely.

## GitHub Public Monitoring

```env
GITHUB_TOKEN=your_token_here
GITHUB_SEARCH_QUERIES=
GITHUB_MAX_RESULTS_PER_QUERY=30
GITHUB_MAX_QUERIES_PER_RUN=20
GITHUB_MAX_FILE_FETCHES_PER_RUN=50
```

- `GITHUB_TOKEN`: token for public code search (never logged).
- `GITHUB_SEARCH_QUERIES`: optional comma-separated queries added globally (no organization or risk category tag).
- `GITHUB_MAX_RESULTS_PER_QUERY`: max search results requested per query (default `30`).
- `GITHUB_MAX_QUERIES_PER_RUN`: max configured queries executed per scan (default `20`).
- `GITHUB_MAX_FILE_FETCHES_PER_RUN`: max raw file content fetch attempts per scan (default `50`).

## Detection Document Schema

Each stored detection includes:

| Field | Description |
|-------|-------------|
| `source` | Collector source (`github`, `mock_paste`, …) |
| `source_url` | Public URL when available |
| `title` | Short title |
| `organization` | Optional affected entity; usually empty/unknown in global-first mode |
| `risk_category` | Global risk profile key (e.g. `env_files`, `api_keys`) |
| `confidence` | `high`, `medium`, or `low` based on content evidence |
| `matched_watchlist` | Optional affected-entity watch terms when organization correlation is enabled |
| `detected_indicators` | Indicator categories (emails, secrets, …) |
| `redacted_text` | Redacted body text |
| `risk_score` | Numeric score |
| `severity` | `low`, `medium`, or `high` |
| `status` | Analyst workflow status (`new`, `reviewed`, `ignored`, `confirmed`, `false_positive`, `escalated`) |
| `review_note` | Optional analyst note |
| `reviewed_by` | Optional analyst identifier |
| `reviewed_at` | Timestamp when status was last reviewed |
| `detection_hash` | Deduplication hash |
| `collected_at` | Collection timestamp |
| `processed_at` | Processing timestamp |

Additional fields such as `matched_emails` and `matched_domains` support analysis in Kibana.

## API Endpoints

- `GET /`
- `GET /health`
- `GET /dashboard` - React analyst dashboard SPA
- `GET /dashboard/*` - React dashboard routes served from `frontend/dist`
- `GET /detections` - list detections with optional filters
- `PATCH /detections/{detection_hash}/status` - analyst review workflow
- `GET /analytics/summary` - aggregated detection statistics
- `GET /analytics/timeline` - detection counts over time
- `GET /analytics/source-health` - best-effort source status for the dashboard
- `GET /analytics/charts` - filtered chart aggregations for the dashboard
- `GET /analytics/collection-runs` - persisted collection run observability
- `GET /analytics/correlations` - cross-source correlation groups
- `GET /analytics/intelligence-summary` - deterministic analyst summary
- `GET /analytics/source-diagnostics` - per-query/feed/channel diagnostics from latest runs
- `GET /debug/collection-state` - compact incremental collector state
- `GET /debug/github-config` - read-only GitHub config status without secret values
- `GET /debug/google-alerts-config` - read-only Google Alerts config status
- `GET /debug/telegram-config` - read-only Telegram config status
- `POST /scan/mock`
- `POST /scan/google-alerts`
- `POST /scan/telegram`
- `POST /scan/github`
- `DELETE /admin/dev/mock-data` when `APP_ENV=development`

### React dashboard

Open the monitoring dashboard after starting the stack:

http://localhost:8000/dashboard

The dashboard is a multi-page React application, not a single embedded HTML file. Routes:

- `/dashboard` - global exposure overview, source health, lifetime totals, recent detections, and metric explanations
- `/dashboard/correlations` - grouped risks related by organization, domain, CVE, keyword, secret type, or similar title
- `/dashboard/intelligence` - deterministic intelligence summary and recommended analyst actions
- `/dashboard/github` - global GitHub exposure monitoring, query-window state, GitHub runs, and GitHub detections
- `/dashboard/google-alerts` - public breach/news monitoring, feed state, feed counters, and Google Alerts detections
- `/dashboard/telegram` - Telegram OSINT/CVE intelligence, channel state, and Telegram detections
- `/dashboard/detections` - global detection explorer with advanced filters and a details modal
- `/dashboard/runs` - collection run observability for explaining why totals did not change
- `/dashboard/state` - compact incremental collection state with raw-state modal
- `/dashboard/diagnostics` - per-source query/feed/channel collection diagnostics
- `/dashboard/settings` - read-only config/API health visibility without secret values

The dashboard is organized as:

- `frontend/src/api` for relative-path API calls and consistent error handling
- `frontend/src/hooks` for independent data loading and refresh behavior
- `frontend/src/layout` for sidebar, topbar, scan buttons, manual refresh, and auto-refresh
- `frontend/src/pages` for route-level source views
- `frontend/src/components` for reusable cards, tables, badges, modals, charts, and empty/error states

The dashboard is a multi-source monitoring cockpit for:

- **GitHub exposure**: technical exposure evidence such as repositories, files, suspicious paths, possible secrets, and validated secret counts.
- **Google Alerts**: public breach/news signals that require validation before being treated as evidence.
- **Telegram OSINT**: public-channel CVE/security intelligence signals that require validation.

The React pages load data independently from `/analytics/summary`, `/analytics/source-health`, `/analytics/collection-runs`, `/analytics/correlations`, `/analytics/intelligence-summary`, `/analytics/source-diagnostics`, `/debug/collection-state`, `/detections`, and the read-only debug config endpoints. If one endpoint fails, the affected card or page shows an error while the rest of the dashboard continues to render.

The detection list supports filters for `source`, `signal_type`, optional `organization`/affected entity, `category`, `country`, `risk_category`, `confidence`, `severity`, `status`, `date_range`, and `search`. Source-specific pages add local filters such as secret type or Telegram channel where those values are stored inside detection documents.

Date range values are `1h`, `24h`, `7d`, `30d`, and `all`. Search matches titles, organizations, source URLs, previews, evidence text, CVE IDs, alert names, detected keywords, and secret types.

The dashboard auto-refreshes every 60 seconds, shows the last refresh time, and pauses refresh while the evidence modal is open. The auto-refresh toggle can pause or resume polling manually.

Collection buttons:

- `Collect all` queues GitHub, Google Alerts, and Telegram scans.
- `GitHub` queues only the GitHub scan.
- `Google Alerts` queues only the Google Alerts scan.
- `Telegram` queues only the Telegram scan.

The source-health panel reports collector/API operational health, not detection volume. A source is `healthy` when the latest scan executed normally with no collector errors, even if it indexed zero detections. `warning` is reserved for partial or recoverable technical issues such as rate limits, incomplete query/feed/channel results, or collector errors that did not crash the scan. `error` means the source could not run, authentication failed, required configuration is missing, or the collector crashed. `disabled` means the source is intentionally turned off.

The panel separates `Technical Status` from `Last Scan Result` and finding counters. Scan counters such as indexed count, duplicates skipped, warnings, and errors are written by the actual Celery task into Redis and persisted collection runs. If no task has run yet, unavailable values show `unknown`; the UI does not fabricate scan metrics or fall back to demo detections.

Metric interpretation:

- **Total indexed** is the lifetime count of redacted detection documents currently stored in Elasticsearch.
- **Collected last scan** is raw source activity seen by the collector before dedupe and noise filtering.
- **Indexed last scan** is the number of new detections written during the latest collection run.
- **Duplicates skipped** are already-known detection hashes skipped by the deduplicator.
- **Errors / warnings** describe technical collector issues, not whether the source produced findings.
- A source can be healthy with zero indexed detections when the scan succeeded but found only duplicates, noise, informational entries, or no new source items. In that case the dashboard shows the zero count plainly with a message such as `No new validated detections were indexed`.

`Needs validation` means the detection came from a public report or OSINT channel and should be manually checked before escalation. GitHub findings are shown as technical exposure evidence; Google Alerts and Telegram findings are shown as validation-required signals.

### Analyst review workflow

The detection drawer has a **Review** tab. Analysts can change the status, add a review note, and save without reloading the dashboard. The drawer updates immediately after the backend accepts the change.

List detections (filters are optional):

```bash
curl "http://localhost:8000/detections?source=github&risk_category=env_files&confidence=high&severity=high&status=new&limit=20"
```

Telegram CVE intelligence filter example:

```bash
curl "http://localhost:8000/detections?source=telegram&category=cve_intelligence&severity=high&confidence=medium&limit=20"
```

Update detection status:

```bash
curl -X PATCH "http://localhost:8000/detections/<detection_hash>/status" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "reviewed",
    "review_note": "Checked manually",
    "reviewed_by": "analyst"
  }'
```

Allowed `status` values: `new`, `reviewed`, `ignored`, `confirmed`, `false_positive`, `escalated`.

Invalid status returns `400`. Missing detection returns `404`.

### Alerting

High-severity detections trigger Telegram and email alert attempts after they are saved. Missing alert environment variables do not crash scans; the alert sender logs a clear skip reason.

Telegram alerting:

```env
TELEGRAM_BOT_TOKEN=123456:bot-token
TELEGRAM_CHAT_ID=123456789
```

Email alerting:

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=alerts@example.com
SMTP_PASSWORD=secret
ALERT_EMAIL_TO=soc@example.com,security@example.com
```

Duplicate alert sends are avoided per detection/channel by recording alert state in the `collection_state` index under the `alerts` source.

### Detection analytics

Summary dashboard data (Elasticsearch aggregations on `breach_signals`):

```bash
curl "http://localhost:8000/analytics/summary"
```

Returns `total_detections`, breakdowns by `source`, optional affected entity, `risk_category`, `confidence`, `severity`, and `status`, plus the latest 10 detections.

Timeline counts bucketed by `processed_at`:

```bash
curl "http://localhost:8000/analytics/timeline?interval=day&days=7"
curl "http://localhost:8000/analytics/timeline?interval=hour&days=2"
```

- `interval`: `hour` or `day` (invalid values return `400`)
- `days`: lookback window (default `7`, max `90`)

Cross-source correlations:

```bash
curl "http://localhost:8000/analytics/correlations"
```

Intelligence summary:

```bash
curl "http://localhost:8000/analytics/intelligence-summary"
```

Source diagnostics:

```bash
curl "http://localhost:8000/analytics/source-diagnostics"
```

## Mock Data Cleanup

```bash
curl -X DELETE http://localhost:8000/admin/dev/mock-data
```

Development only. Deletes documents where `source` is `mock_paste`; does not delete GitHub detections.

## Notes

All sensitive values are redacted before storage. Demo mock paste files use fake indicators only and are not part of the main GitHub monitoring pipeline.


Invoke-RestMethod -Method Post http://localhost:8000/scan/github
