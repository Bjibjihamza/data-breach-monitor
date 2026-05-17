# Platform Scope

## What This Platform Is

**External Data Exposure & Breach Monitoring Platform** — a defensive, OSINT-based system that detects publicly exposed sensitive data across authorized public sources.

### In scope

Monitoring for signals such as:

- Leaked credentials
- API keys and tokens
- Database URIs and passwords
- Exposed `.env` files and cloud keys
- Global public GitHub exposure patterns
- Optional affected-entity correlation via YAML profiles when explicitly enabled
- Future authorized public OSINT sources

### Out of scope

This platform is **not** a generic vulnerability scanner and must not be used for offensive security:

- Port scanning
- CVE exploitation or web vulnerability scanning
- Pentesting automation
- Malware analysis
- Exploitation logic or offensive actions

## Monitoring Model

Monitoring is **global-first** with optional affected-entity correlation:

1. **Global risk profiles** (`app/watchlists/global_risks.yml`) define organization-agnostic GitHub queries by exposure category (e.g. `env_files`, `api_keys`, `private_keys`).
2. **Environment queries** (`GITHUB_SEARCH_QUERIES`) add ad-hoc global exposure queries.
3. **Organization profiles** are disabled by default and are not required for GitHub scanning. If `ORGANIZATION_WATCHLISTS_ENABLED=true`, profiles from `config/organizations_watchlist.yml` or `app/watchlists/organizations/` can add affected-entity correlation and optional extra queries.

GitHub monitoring always fetches file content and stores only detections where the content contains exposure evidence (not query metadata alone).

## Data Sources

| Source        | Role                                      |
|---------------|-------------------------------------------|
| `github`      | First real public collector (GitHub Search) |
| `mock_paste`  | Local testing/demo only                   |
| Others        | Placeholders for future authorized use    |

Detections are stored in Elasticsearch index `breach_signals` with redacted content only.
