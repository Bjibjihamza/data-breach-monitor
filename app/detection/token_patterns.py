"""Shared token prefix patterns for extraction, validation, and redaction."""

from __future__ import annotations

import re

# Provider token prefixes (value-only detection)
GITHUB_TOKEN_RE = re.compile(
    r"^(?:gh[oprsu]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{20,}_[A-Za-z0-9_]{20,})$"
)
GITLAB_TOKEN_RE = re.compile(r"^glpat-[A-Za-z0-9_-]{20,}$")
AWS_ACCESS_KEY_RE = re.compile(r"^(?:AKIA|ASIA)[A-Z0-9]{16}$")
AWS_SECRET_RE = re.compile(r"^[A-Za-z0-9/+=]{40}$")
STRIPE_LIVE_SECRET_RE = re.compile(r"^sk_live_[A-Za-z0-9]{16,}$")
SLACK_TOKEN_RE = re.compile(r"^xox[abprs]-[A-Za-z0-9-]{10,}$")
JWT_RE = re.compile(r"^eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}$")
SENDGRID_KEY_RE = re.compile(r"^SG\.[A-Za-z0-9_-]{20,}$")
GOOGLE_API_KEY_RE = re.compile(r"^AIza[0-9A-Za-z_-]{35}$")
GOOGLE_OAUTH_TOKEN_RE = re.compile(r"^ya29\.[0-9A-Za-z_-]+$")
DIGITALOCEAN_TOKEN_RE = re.compile(r"^dop_v1_[a-f0-9]{64}$")
NPM_TOKEN_RE = re.compile(r"^npm_[A-Za-z0-9]{36,}$")
RESEND_API_KEY_RE = re.compile(r"^re_[A-Za-z0-9]{24,}$")
LINEAR_API_KEY_RE = re.compile(r"^lin_api_[A-Za-z0-9]{40,}$")
NOTION_TOKEN_RE = re.compile(r"^secret_[A-Za-z0-9]{43,}$")
RENDER_API_KEY_RE = re.compile(r"^rnd_[A-Za-z0-9]{32,}$")
LEMON_SQUEEZY_KEY_RE = re.compile(r"^lsq_(?:live|test)_[A-Za-z0-9]{20,}$")
RAILWAY_TOKEN_RE = re.compile(r"^(?:railway|rwy)_[A-Za-z0-9_-]{20,}$", re.IGNORECASE)

BARE_TOKEN_SCAN_RE = re.compile(
    r"\b(?:"
    r"gh[oprsu]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{20,}_[A-Za-z0-9_]{20,}|"
    r"glpat-[A-Za-z0-9_-]{20,}|"
    r"xox[abprs]-[A-Za-z0-9-]{10,}|sk_live_[A-Za-z0-9]{16,}|"
    r"AKIA[A-Z0-9]{16}|ASIA[A-Z0-9]{16}|"
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|"
    r"SG\.[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{35}|ya29\.[0-9A-Za-z_-]+|"
    r"dop_v1_[a-f0-9]{64}|npm_[A-Za-z0-9]{36,}|"
    r"re_[A-Za-z0-9]{24,}|lin_api_[A-Za-z0-9]{40,}|secret_[A-Za-z0-9]{43,}|"
    r"rnd_[A-Za-z0-9]{32,}|lsq_(?:live|test)_[A-Za-z0-9_-]{20,}|"
    r"(?:railway|rwy)_[A-Za-z0-9_-]{20,}"
    r")\b",
    re.IGNORECASE,
)

REDACT_BARE_TOKEN_RE = BARE_TOKEN_SCAN_RE

DOCKER_ENV_ARG_RE = re.compile(
    r"^\s*(?:ENV|ARG)\s+(?P<key>[A-Za-z_][A-Za-z0-9_]*)(?:\s*=\s*|\s+)(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
YAML_KV_RE = re.compile(
    r"^\s{2,}(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*(?P<value>.*?)\s*$"
)
PLIST_STRING_RE = re.compile(
    r"<key>(?P<key>[^<]+)</key>\s*<string>(?P<value>[^<]*)</string>",
    re.IGNORECASE,
)
K8S_BLOCK_HEADERS = frozenset({"stringdata:", "data:"})
