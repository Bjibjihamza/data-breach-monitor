# SaaS Transformation Plan — External Data Exposure & Threat Intelligence Monitoring Platform

## 1. Product Vision

The current project is a cybersecurity monitoring dashboard that collects public exposure signals from GitHub, Google Alerts / RSS, and Telegram. The next strategic goal is to transform it into a reusable SaaS product that organizations can use to monitor whether their sensitive information, assets, brands, domains, credentials, or internal project names appear in public or semi-public sources.

The target product is:

> A multi-tenant External Data Exposure & Threat Intelligence Monitoring SaaS for organizations.

Instead of being configured once through `.env` files, the platform should allow each organization to configure its own monitoring scope through the UI.

Current model:

```text
One global dashboard
→ one global configuration
→ scans GitHub, News/RSS, Telegram
→ displays all results together
```

Target SaaS model:

```text
Many organizations
→ each organization has its own domains, keywords, assets, sources, and alert rules
→ platform scans public sources
→ each organization sees only its own detections, alerts, reports, and scan history
```

The core product promise:

```text
“Tell us who you are and what belongs to you. We monitor public sources and alert you when your data, credentials, brand, or sensitive assets appear exposed.”
```

---

## 2. Strategic Product Positioning

Possible product names / positioning:

- External Data Exposure Monitoring Platform
- Brand & Credential Exposure Intelligence SaaS
- Public Leak & Threat Intelligence Monitoring Platform
- Cyber Exposure Monitoring for Organizations
- SaaS for leaked credentials, GitHub secrets, Telegram intelligence, and breach news monitoring

The platform should not be only a “dashboard”. It should become a workflow product:

```text
Configure assets → collect signals → score risks → alert users → triage detections → generate reports
```

---

## 3. Target Users

### 3.1 Primary users

| User type | Needs |
|---|---|
| Security analyst | Detect leaks, triage detections, investigate evidence |
| SOC team | Receive alerts and escalate incidents |
| GRC / Risk team | Track exposure risk and generate reports |
| IT administrator | Configure organization assets and alert channels |
| Executive / manager | View high-level risk status and trend reports |

### 3.2 SaaS roles

| Role | Permissions |
|---|---|
| Owner/Admin | Manage organization, users, billing later, settings |
| Security Analyst | View, triage, assign, comment, escalate detections |
| Viewer | Read-only access to dashboards and reports |
| Auditor | Export reports and review history |
| Integration Manager | Configure Slack/Teams/Email/Webhook integrations |

Every user must belong to at least one organization.

Every query and detection must be scoped by:

```text
organization_id / tenant_id
```

This is the most important SaaS backend change.

---

## 4. What the Organization Configures

The SaaS should replace hardcoded `.env` monitoring values with organization-specific configuration screens.

### 4.1 Organization identity

The onboarding wizard should ask for:

| Field | Purpose |
|---|---|
| Company / organization name | Brand matching and reports |
| Legal name | Executive reports / compliance |
| Industry | Industry-specific scoring |
| Country / region | Regional threat intelligence |
| Main website | Primary monitored domain |
| Logo | Dashboard and reports |
| Description | Context for analysts |

Example:

```text
Organization name: ENSA Tétouan
Main domain: ensat.ac.ma
Industry: Education
Country: Morocco
```

---

### 4.2 Domains and subdomains

The company should configure domains it owns:

```text
company.com
company.ma
api.company.com
mail.company.com
*.company.com
```

The platform should monitor:

- domain mentions
- subdomain mentions
- email addresses using the domain
- GitHub files containing the domain
- Telegram posts mentioning the domain
- news/RSS articles mentioning the domain
- later: phishing domains / typo-squatting / certificate transparency

Important distinction:

```text
Public mention of a domain ≠ breach
Domain + credential / leak / dump context = higher risk
```

---

### 4.3 Email patterns

The company configures official email domains and patterns:

```text
@company.com
@company.ma
firstname.lastname@company.com
support@company.com
security@company.com
```

Use cases:

- employee email found in breach mention
- corporate email in Telegram leak post
- GitHub file containing company email and credential context
- credential dump references

Severity logic:

```text
public contact email only → informational
employee email + password/dump/leak context → high
email + credential/secret evidence → critical
```

---

### 4.4 Brand names and keywords

The company should configure:

- official brand names
- abbreviations
- subsidiaries
- product names
- internal project names
- old company names
- public platform names

Example:

```text
KOSTAL
KOSTAL Morocco
KOMOR
Launch Status Portal
P08330
PWS
```

These should be used across GitHub, News/RSS, and Telegram.

Important scoring rule:

```text
keyword-only match → low/informational
keyword + leak/credential/ransomware/dump context → medium/high
keyword + validated secret or credential → high/critical
```

---

### 4.5 Sensitive technical identifiers

The platform becomes stronger if the customer can add technical identifiers:

| Asset type | Examples |
|---|---|
| GitHub organizations | `company`, `company-labs` |
| GitHub repositories | `backend-api`, `mobile-app` |
| API domains | `api.company.com` |
| Cloud project IDs | GCP project IDs, Azure tenant names |
| Package names | npm, PyPI, Maven package names |
| Mobile app IDs | `com.company.mobile` |
| Internal project names | `core-payments`, `launch-portal` |
| Database host patterns | `company-prod-db`, `db.company.internal` |

These identifiers help find real leaks in public code and OSINT sources.

---

### 4.6 GitHub monitoring configuration

The company should configure:

- company domains
- email domains
- GitHub organizations
- GitHub repositories
- internal project names
- product names
- technology identifiers

There should be two GitHub scan modes:

| Mode | Meaning |
|---|---|
| Global exposure scan | Search all public GitHub for company identifiers |
| Owned asset scan | Monitor company-owned GitHub orgs/repos |

This distinction is important:

```text
Secret in company-owned repo → internal remediation
Secret in third-party public repo → external exposure / takedown workflow
```

Example generated queries:

```text
"company.com" filename:.env
"@company.com" password
"api.company.com" DATABASE_URL
"company-prod" API_KEY
"company-mobile" SECRET_KEY
```

---

### 4.7 News / RSS / Google Alerts configuration

The company should monitor news and RSS sources for:

```text
company name breach
company name ransomware
company domain leak
company product vulnerability
company sector cyberattack
country-specific incidents
```

The SaaS should offer:

- default managed intelligence feeds
- custom RSS feed URLs
- optional Google Alert RSS URLs
- region-specific feeds
- industry-specific feeds

Types of news intelligence:

| Type | Example |
|---|---|
| Breach news | “Company X data exposed” |
| Ransomware | “Company X claimed by ransomware group” |
| Vulnerability | “Product Y critical CVE” |
| Sector threat | “Banks in Morocco targeted” |
| Brand mention | “Company X appears in leak forum article” |

---

### 4.8 Telegram / OSINT configuration

Telegram can be offered in two modes.

#### Managed mode

The platform maintains default channels:

- CVE channels
- breach announcement channels
- leak monitoring channels
- ransomware channels
- threat actor discussion channels

The customer only configures their watchlist:

```text
company names
email domains
domains
project names
product names
```

#### Advanced mode

The customer can add:

```text
channel username
channel URL
source category
language
risk level
```

For MVP, managed mode is better. The customer should not need to understand Telegram internals.

---

### 4.9 Alert rules

The company configures when and where to receive alerts.

Alert channels:

- Email
- Slack
- Microsoft Teams
- Telegram bot
- Webhook
- Dashboard only

Alert preferences:

```text
Critical → immediately
High → immediately or hourly
Medium → daily digest
Low → dashboard only
Informational → dashboard only
```

Alert rule examples:

```text
If validated secret found → send critical alert immediately
If employee email appears with password context → send high alert
If brand mention appears in news → dashboard only
If GitHub template file contains placeholder → ignore
```

---

### 4.10 Risk scoring preferences

Each organization can use default scoring, but later the SaaS can allow industry-specific profiles.

Examples:

| Industry | Scoring preference |
|---|---|
| Banking | customer data / credentials = critical |
| Healthcare | patient data / HIPAA-related breach = critical |
| SaaS | API keys / cloud tokens = critical |
| Education | student email dump = high |
| Manufacturing | supplier / internal project leaks = high |

MVP can start with one default risk model, then add profiles later.

---

## 5. SaaS Dashboard Structure

### 5.1 Organization selector

At the top of the app:

```text
Current organization: AcmeBank
```

If a user belongs to multiple organizations:

```text
AcmeBank
AcmePay
AcmeCloud
```

All dashboard queries must be scoped to the selected organization.

---

### 5.2 Recommended SaaS pages

| Page | Purpose |
|---|---|
| Overview | Executive risk summary for selected organization |
| Live Scan Status | Current scan execution state |
| Detections | All detections with filtering and triage |
| GitHub Intelligence | Public code / secret exposure |
| News Intelligence | RSS / Google Alerts / news mentions |
| Telegram Intelligence | Telegram OSINT mentions |
| Assets | Domains, emails, keywords, GitHub orgs, projects |
| Watchlists | Detailed monitoring rules |
| Alert Rules | Severity thresholds and notification rules |
| Integrations | Email, Slack, Teams, webhook, Telegram bot |
| Reports | Weekly/monthly exports |
| Users & Roles | Organization access control |
| Settings | Organization-level settings |

---

### 5.3 Onboarding wizard

A new SaaS organization should start with a guided onboarding flow.

Steps:

1. Organization identity
2. Domains and subdomains
3. Email patterns
4. Brand names and keywords
5. Technical assets
6. GitHub monitoring setup
7. News / RSS monitoring setup
8. Telegram / OSINT monitoring setup
9. Alert channels
10. Scan schedule
11. Review and start monitoring

The onboarding output should create the organization watchlist automatically.

---

## 6. Backend Architecture Changes

### 6.1 Multi-tenant entities

Core data model:

```text
Organization
 ├── Users
 ├── Domains
 ├── EmailPatterns
 ├── Keywords
 ├── TechnicalAssets
 ├── GitHubAssets
 ├── NewsFeeds
 ├── TelegramRules
 ├── AlertRules
 ├── Integrations
 ├── ScanRuns
 └── Detections
```

Every detection should include:

```text
organization_id
organization_name
matched_asset
matched_rule
matched_value
source
severity
risk_score
status
```

---

### 6.2 Tenant-aware scans

Current scans are global. SaaS scans should become organization-aware.

Examples:

```text
POST /organizations/{org_id}/scan/all
POST /organizations/{org_id}/scan/github
POST /organizations/{org_id}/scan/google-alerts
POST /organizations/{org_id}/scan/telegram
```

Each scan should:

- load the organization watchlist
- generate source-specific queries
- collect source data
- match data against organization assets
- store detections with `organization_id`
- update organization-specific run status

---

### 6.3 Tenant-aware dashboards

API queries should become organization-scoped.

Examples:

```text
GET /organizations/{org_id}/detections
GET /organizations/{org_id}/analytics/summary
GET /organizations/{org_id}/scan/status
GET /organizations/{org_id}/collector-state
GET /organizations/{org_id}/reports
```

Security rule:

```text
A user must never see another organization’s detections.
```

---

### 6.4 Source configuration split

Separate platform-managed sources from customer watchlists.

#### Platform-managed

```text
default Telegram channels
default RSS threat feeds
default GitHub secret queries
secret validation rules
risk scoring engine
```

#### Customer-managed

```text
organization domains
email patterns
keywords
GitHub orgs/repos
alert destinations
scan frequency
risk preferences
```

This gives a good SaaS UX: customers configure what belongs to them, not how the entire scanning engine works.

---

## 7. Detection Model for SaaS

A SaaS detection should answer:

```text
What was found?
Where was it found?
Which organization does it affect?
Which asset matched?
How risky is it?
What should the analyst do?
```

Recommended detection fields:

```json
{
  "organization_id": "org_123",
  "organization_name": "AcmeBank",
  "source": "github",
  "severity": "critical",
  "risk_score": 95,
  "title": "Possible GitHub credential exposure",
  "matched_asset": "api.acmebank.com",
  "matched_rule": "domain_match + database_url",
  "source_url": "https://github.com/...",
  "evidence_summary": "DATABASE_URL with credentials found in public repository",
  "redacted_text": "DATABASE_URL=[REDACTED_DB_URI]",
  "recommended_action": [
    "Rotate exposed credential immediately",
    "Check database access logs",
    "Contact repository owner for takedown",
    "Mark detection as escalated"
  ],
  "status": "new",
  "assigned_to": null,
  "created_at": "..."
}
```

---

## 8. Alert Content

Alerts should not just say “detection found”. They should be actionable.

Alert template:

```text
Critical: Possible public credential exposure detected

Organization: AcmeBank
Source: GitHub
Matched asset: api.acmebank.com
Evidence: DATABASE_URL with credentials found in public repository
Severity: Critical
Risk score: 95
Source URL: https://github.com/...

Recommended action:
1. Rotate the exposed credential immediately.
2. Check access logs.
3. Contact the repository owner.
4. Mark detection as escalated in the dashboard.
```

---

## 9. Triage Workflow

Detections should support a security workflow:

Statuses:

```text
new
reviewed
false_positive
escalated
resolved
ignored
```

Useful fields:

```text
assigned_to
review_note
reviewed_by
reviewed_at
resolution_note
resolved_at
severity_override
```

This makes the product useful for real analysts.

---

## 10. Reports

Reports are important for SaaS value.

Possible reports:

- weekly exposure summary
- monthly executive report
- source-specific report
- critical detections report
- false positive report
- remediation status report

Report sections:

```text
Executive summary
Top risks
Source breakdown
Critical detections
Trend over time
Remediation status
Recommended actions
```

Formats:

```text
PDF
CSV
JSON export
```

---

## 11. MVP SaaS Scope

Do not build everything at once.

The best MVP:

### Organization setup

Each organization can configure:

- organization name
- domains
- email patterns
- keywords
- GitHub orgs/repos
- alert email/webhook
- scan frequency

### Source monitoring

MVP sources:

- GitHub
- Google Alerts / RSS
- Telegram managed channels

### Dashboard

Organization-specific:

- overview
- detections
- live scan status
- source pages
- assets/watchlist
- alert rules

### Alerts

- email alert
- webhook alert

### Reports

- simple PDF/CSV export later

---

## 12. Recommended Roadmap

### Phase A — SaaS architecture design

Goal:

```text
Design multi-tenant data model and API structure.
```

Tasks:

- define Organization entity
- define organization watchlists
- define user roles
- define organization-scoped detections
- define organization-scoped scan runs
- decide storage model

---

### Phase B — Organization onboarding

Goal:

```text
Replace .env-only monitoring configuration with UI-based organization configuration.
```

Tasks:

- create organization setup page
- add domains, emails, keywords, GitHub assets
- store watchlist in database / Elasticsearch / config store
- generate source-specific scan rules from watchlist

---

### Phase C — Tenant-aware scans

Goal:

```text
Run GitHub, News, and Telegram scans for a specific organization.
```

Tasks:

- add org_id to scan endpoints
- load org watchlist
- add org_id to detections
- add org_id to collection runs
- filter dashboard by org_id

---

### Phase D — Alerting and integrations

Goal:

```text
Notify customers when relevant detections appear.
```

Tasks:

- configure alert rules
- add email alerts
- add webhook alerts
- add Slack / Teams later
- severity-based alert routing

---

### Phase E — Analyst workflow

Goal:

```text
Make detections actionable.
```

Tasks:

- assign detections
- status workflow
- review notes
- false positive marking
- escalation
- resolution tracking

---

### Phase F — Reports

Goal:

```text
Make the product useful for managers and audits.
```

Tasks:

- weekly summary
- monthly report
- PDF export
- CSV export
- source breakdown

---

### Phase G — Billing and plans later

Do not start with billing.

Build the security workflow first.

Future pricing dimensions:

- number of organizations
- number of monitored domains
- number of scans per day
- number of users
- number of integrations
- retention period

---

## 13. Important Technical Principles

### 13.1 Everything must be organization-scoped

Every entity should eventually include:

```text
organization_id
```

This applies to:

- detections
- scan runs
- collector state
- alert rules
- watchlists
- reports
- integrations
- users

---

### 13.2 Do not expose raw secrets

Never store or display raw credentials.

Always use:

```text
redacted_text
evidence_summary
secret_type
risk_score
```

---

### 13.3 Avoid noisy alerts

SaaS success depends on low noise.

Rules:

```text
placeholder-only → ignore
template-only → low/ignore
brand-only → informational
validated secret → high/critical
credential dump context → high
```

---

### 13.4 Make alerts actionable

Every alert should include:

```text
what happened
why it matters
matched organization asset
evidence
recommended action
```

---

### 13.5 Keep platform-managed intelligence separate

Customers should configure their assets.
The platform should manage source logic.

Good SaaS UX:

```text
Customer: “Here are my domains and brands.”
Platform: “We know how to monitor them.”
```

---

## 14. What To Do After One Week

When returning to this project, continue with:

```text
Phase A — SaaS architecture design
```

Do not start by coding UI.

Start by designing:

1. Organization model
2. Watchlist model
3. Detection model with `organization_id`
4. Scan run model with `organization_id`
5. Tenant-aware API routes
6. Access control / roles
7. Migration plan from current global config

Suggested first task:

```text
Create a SaaS architecture design document for multi-tenant organization monitoring.
```

Then implement in this order:

```text
1. Organization entity
2. Organization watchlist config
3. Organization-scoped detections
4. Organization-scoped scan endpoints
5. Organization selector in frontend
6. Onboarding wizard
```

---

## 15. Current Project Status Before SaaS Transformation

Completed technical phases:

| Phase | Status |
|---|---|
| Phase 1 | GitHub pipeline audit completed |
| Phase 2 | GitHub false-positive reduction completed |
| Phase 3 | GitHub true-positive coverage expansion completed |
| Phase 4 | Live scan status and source-level controls completed |

Known recent backend issue to remember:

```text
Telegram scan had a stats mismatch:
TelegramCollectionStats missing channels_processed.
Also Elasticsearch index creation needed idempotent handling for resource_already_exists_exception.
```

This should be fixed before or during the next cleanup pass.

---

## 16. Summary

The product direction is now:

```text
From: one internal monitoring dashboard
To: multi-tenant SaaS exposure monitoring platform
```

Core SaaS transformation:

```text
Organization-specific configuration
Organization-scoped scans
Organization-scoped detections
Organization-specific alerts
Reusable dashboard for many customers
```

The most important principle:

```text
Everything must become organization-scoped.
```

Without organization scoping, the product is only a dashboard with settings.
With organization scoping, onboarding, alerting, and roles, it becomes a real SaaS product.
