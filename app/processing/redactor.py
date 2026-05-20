from __future__ import annotations

import re

from app.detection.token_patterns import BARE_TOKEN_SCAN_RE, REDACT_BARE_TOKEN_RE
from app.processing.detector import (
    API_KEY_ASSIGNMENT_RE,
    AWS_ACCESS_KEY_RE,
    BEARER_TOKEN_RE,
    DB_URI_RE,
    EMAIL_RE,
    GITHUB_TOKEN_RE,
    JWT_RE,
    OPENAI_KEY_RE,
    PASSWORD_ASSIGNMENT_RE,
    TOKEN_ASSIGNMENT_RE,
)

SLACK_TOKEN_RE = re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")
STRIPE_LIVE_KEY_RE = re.compile(r"\bsk_live_[A-Za-z0-9]{16,}\b")
TWILIO_AUTH_TOKEN_ASSIGNMENT_RE = re.compile(
    r"\b(TWILIO_AUTH_TOKEN)\b\s*[:=]\s*[\"']?[A-Fa-f0-9]{32}[\"']?",
    re.IGNORECASE,
)
AWS_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b(AWS_SECRET_ACCESS_KEY)\b\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{40}[\"']?",
    re.IGNORECASE,
)
_NAMED_ASSIGNMENT_RE = re.compile(
    r"\b(DB_PASSWORD|DATABASE_URL|API_KEY|SECRET_KEY|JWT_SECRET|TWILIO_AUTH_TOKEN|AWS_SECRET_ACCESS_KEY|"
    r"VERCEL_TOKEN|SUPABASE_SERVICE_ROLE_KEY|SUPABASE_DB_PASSWORD|SUPABASE_ANON_KEY|"
    r"CLOUDFLARE_API_TOKEN|CF_API_TOKEN|RAILWAY_TOKEN|RENDER_API_KEY|LINEAR_API_KEY|"
    r"NOTION_TOKEN|NOTION_API_KEY|RESEND_API_KEY|LOOPS_API_KEY|"
    r"LEMONSQUEEZY_API_KEY|LEMON_SQUEEZY_API_KEY|PLANETSCALE_PASSWORD)\b\s*[:=]\s*[\"']?[^\s\"']+[\"']?",
    re.IGNORECASE,
)
PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
    re.IGNORECASE,
)
DOCKER_ENV_ARG_RE = re.compile(
    r"^(\s*(?:ENV|ARG)\s+)([A-Za-z_][A-Za-z0-9_]*)(?:\s*=\s*|\s+)([^\s#]+)",
    re.IGNORECASE | re.MULTILINE,
)
K8S_YAML_VALUE_RE = re.compile(
    r"^(\s{2,}[A-Za-z_][A-Za-z0-9_.-]*\s*:\s*)([^\s#]+)",
    re.MULTILINE,
)


def mask_email_value(email: str) -> str:
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = f"{local[0]}***"
    else:
        masked_local = f"{local[0]}***{local[-1]}"
    return f"{masked_local}@{domain}"


def _mask_email(match: re.Match[str]) -> str:
    return mask_email_value(match.group(0))


def _redact_named_assignment(match: re.Match[str]) -> str:
    name = match.group(1)
    if name.upper() == "DATABASE_URL" or DB_URI_RE.search(match.group(0)):
        return f"{name}=[REDACTED_DB_URI]"
    return f"{name}=[REDACTED]"


def _redact_docker_env(match: re.Match[str]) -> str:
    return f"{match.group(1)}{match.group(2)}=[REDACTED]"


def _redact_k8s_value(match: re.Match[str]) -> str:
    return f"{match.group(1)}[REDACTED]"


def redact_sensitive_values(text: str) -> str:
    redacted = PRIVATE_KEY_BLOCK_RE.sub("[REDACTED_PRIVATE_KEY_BLOCK]", text)
    redacted = EMAIL_RE.sub(_mask_email, redacted)
    redacted = DB_URI_RE.sub("[REDACTED_DB_URI]", redacted)
    redacted = BARE_TOKEN_SCAN_RE.sub("[REDACTED_SECRET]", redacted)
    redacted = GITHUB_TOKEN_RE.sub("[REDACTED_SECRET]", redacted)
    redacted = SLACK_TOKEN_RE.sub("[REDACTED_SECRET]", redacted)
    redacted = STRIPE_LIVE_KEY_RE.sub("[REDACTED_SECRET]", redacted)
    redacted = OPENAI_KEY_RE.sub("[REDACTED_SECRET]", redacted)
    redacted = AWS_ACCESS_KEY_RE.sub("[REDACTED_SECRET]", redacted)
    redacted = AWS_SECRET_ASSIGNMENT_RE.sub("AWS_SECRET_ACCESS_KEY=[REDACTED]", redacted)
    redacted = TWILIO_AUTH_TOKEN_ASSIGNMENT_RE.sub("TWILIO_AUTH_TOKEN=[REDACTED]", redacted)
    redacted = JWT_RE.sub("[REDACTED_SECRET]", redacted)
    redacted = BEARER_TOKEN_RE.sub("Bearer [REDACTED_SECRET]", redacted)
    redacted = PASSWORD_ASSIGNMENT_RE.sub("[REDACTED_PASSWORD_ASSIGNMENT]", redacted)
    redacted = API_KEY_ASSIGNMENT_RE.sub("[REDACTED_SECRET_ASSIGNMENT]", redacted)
    redacted = TOKEN_ASSIGNMENT_RE.sub("[REDACTED_SECRET_ASSIGNMENT]", redacted)
    redacted = _NAMED_ASSIGNMENT_RE.sub(_redact_named_assignment, redacted)
    redacted = DOCKER_ENV_ARG_RE.sub(_redact_docker_env, redacted)
    redacted = K8S_YAML_VALUE_RE.sub(_redact_k8s_value, redacted)
    return redacted


def redact_evidence_line(line: str) -> str:
    """Redact a single evidence line with human-readable placeholders for the dashboard."""
    redacted = _NAMED_ASSIGNMENT_RE.sub(_redact_named_assignment, line)
    redacted = EMAIL_RE.sub(_mask_email, redacted)
    redacted = DB_URI_RE.sub("[REDACTED_DB_URI]", redacted)
    redacted = REDACT_BARE_TOKEN_RE.sub("[REDACTED]", redacted)
    redacted = GITHUB_TOKEN_RE.sub("[REDACTED]", redacted)
    redacted = SLACK_TOKEN_RE.sub("[REDACTED]", redacted)
    redacted = STRIPE_LIVE_KEY_RE.sub("[REDACTED]", redacted)
    redacted = OPENAI_KEY_RE.sub("[REDACTED]", redacted)
    redacted = AWS_ACCESS_KEY_RE.sub("[REDACTED]", redacted)
    redacted = AWS_SECRET_ASSIGNMENT_RE.sub("AWS_SECRET_ACCESS_KEY=[REDACTED]", redacted)
    redacted = TWILIO_AUTH_TOKEN_ASSIGNMENT_RE.sub("TWILIO_AUTH_TOKEN=[REDACTED]", redacted)
    redacted = JWT_RE.sub("[REDACTED]", redacted)
    redacted = BEARER_TOKEN_RE.sub("Bearer [REDACTED]", redacted)
    redacted = API_KEY_ASSIGNMENT_RE.sub("[REDACTED]", redacted)
    redacted = TOKEN_ASSIGNMENT_RE.sub("[REDACTED]", redacted)
    redacted = DOCKER_ENV_ARG_RE.sub(_redact_docker_env, redacted)
    redacted = re.sub(
        r"\b(password|passwd|pwd|db_password|database_password)\b\s*[:=]\s*[\"']?[^\s,\"']{8,}[\"']?",
        lambda match: f"{match.group(1)}=[REDACTED]",
        redacted,
        flags=re.IGNORECASE,
    )
    return redacted
