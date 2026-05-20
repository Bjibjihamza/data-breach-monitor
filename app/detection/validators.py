from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

from app.detection.entropy import entropy_confidence, looks_random, shannon_entropy
from app.detection.extractors import ExtractedSecret
from app.detection.noise import is_placeholder_value, normalize_secret_value
from app.detection.token_patterns import (
    AWS_ACCESS_KEY_RE,
    AWS_SECRET_RE,
    DIGITALOCEAN_TOKEN_RE,
    GITHUB_TOKEN_RE,
    GITLAB_TOKEN_RE,
    GOOGLE_API_KEY_RE,
    GOOGLE_OAUTH_TOKEN_RE,
    JWT_RE,
    LEMON_SQUEEZY_KEY_RE,
    LINEAR_API_KEY_RE,
    NOTION_TOKEN_RE,
    NPM_TOKEN_RE,
    RAILWAY_TOKEN_RE,
    RENDER_API_KEY_RE,
    RESEND_API_KEY_RE,
    SENDGRID_KEY_RE,
    SLACK_TOKEN_RE,
    STRIPE_LIVE_SECRET_RE,
)

Confidence = Literal["low", "medium", "high"]
ValidationResult = dict[str, bool | str]

PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+)?PRIVATE KEY-----", re.IGNORECASE)

SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|secret|token|password|passwd|pwd|credential|private[_-]?key|client[_-]?secret|"
    r"vercel|supabase|cloudflare|cf_api|railway|render|linear|notion|resend|loops|lemonsqueezy|"
    r"planetscale|service[_-]?role|anon[_-]?key)",
    re.IGNORECASE,
)
DATABASE_SCHEMES = {"postgres", "postgresql", "mysql", "mongodb", "mongodb+srv", "redis", "mariadb"}

CLOUDFLARE_KEY_NAMES = re.compile(r"(cloudflare|cf_api)", re.IGNORECASE)
VERCEL_KEY_NAMES = re.compile(r"vercel", re.IGNORECASE)
SUPABASE_KEY_NAMES = re.compile(r"supabase", re.IGNORECASE)
RAILWAY_KEY_NAMES = re.compile(r"railway", re.IGNORECASE)
RENDER_KEY_NAMES = re.compile(r"render", re.IGNORECASE)
LINEAR_KEY_NAMES = re.compile(r"linear", re.IGNORECASE)
NOTION_KEY_NAMES = re.compile(r"notion", re.IGNORECASE)
RESEND_KEY_NAMES = re.compile(r"resend", re.IGNORECASE)
LOOPS_KEY_NAMES = re.compile(r"loops", re.IGNORECASE)
LEMON_KEY_NAMES = re.compile(r"lemon[_-]?squeezy|lemonsqueezy", re.IGNORECASE)
NPM_KEY_NAMES = re.compile(r"npm", re.IGNORECASE)
PLANETSCALE_KEY_NAMES = re.compile(r"planetscale|pscale", re.IGNORECASE)


def _result(
    is_valid_candidate: bool,
    secret_type: str,
    confidence: Confidence,
    reason: str,
) -> ValidationResult:
    return {
        "is_valid_candidate": is_valid_candidate,
        "secret_type": secret_type,
        "confidence": confidence,
        "reason": reason,
    }


def _contains_sensitive_key(key: str) -> bool:
    return bool(SENSITIVE_KEY_RE.search(key or ""))


def _validate_database_url(value: str) -> ValidationResult | None:
    parsed = urlparse(value)
    if parsed.scheme.lower() not in DATABASE_SCHEMES:
        return None
    if not parsed.username or not parsed.password or not parsed.hostname:
        return _result(False, "database_url", "low", "database URL missing username/password/host")
    is_placeholder, reason = is_placeholder_value(parsed.password)
    if is_placeholder:
        return _result(False, "database_url", "low", f"database password is placeholder: {reason}")
    if is_placeholder_value(parsed.hostname)[0]:
        return _result(False, "database_url", "low", "database host is localhost/example placeholder")
    return _result(True, "database_url", "high", "database URL contains username, password, and host")


def _validate_by_prefix(value: str, key: str) -> ValidationResult | None:
    lowered_key = key.lower()

    if GITHUB_TOKEN_RE.fullmatch(value):
        return _result(True, "github_token", "high", "GitHub token prefix and length matched")
    if GITLAB_TOKEN_RE.fullmatch(value):
        return _result(True, "gitlab_token", "high", "GitLab personal access token prefix matched")
    if AWS_ACCESS_KEY_RE.fullmatch(value):
        return _result(True, "aws_access_key", "high", "AWS access key id format matched")
    if "aws_secret_access_key" in lowered_key and AWS_SECRET_RE.fullmatch(value):
        return _result(True, "aws_secret_key", "high", "AWS secret access key format matched")
    if STRIPE_LIVE_SECRET_RE.fullmatch(value):
        return _result(True, "stripe_live_secret_key", "high", "Stripe live secret key prefix matched")
    if SLACK_TOKEN_RE.fullmatch(value):
        return _result(True, "slack_token", "high", "Slack token prefix matched")
    if SENDGRID_KEY_RE.fullmatch(value):
        return _result(True, "sendgrid_api_key", "high", "SendGrid API key prefix matched")
    if GOOGLE_API_KEY_RE.fullmatch(value):
        return _result(True, "google_api_key", "high", "Google API key prefix matched")
    if GOOGLE_OAUTH_TOKEN_RE.fullmatch(value):
        return _result(True, "google_oauth_token", "high", "Google OAuth access token prefix matched")
    if DIGITALOCEAN_TOKEN_RE.fullmatch(value):
        return _result(True, "digitalocean_token", "high", "DigitalOcean token prefix matched")
    if NPM_TOKEN_RE.fullmatch(value) or (NPM_KEY_NAMES.search(key) and value.startswith("npm_")):
        return _result(True, "npm_token", "high", "npm auth token prefix matched")
    if RESEND_API_KEY_RE.fullmatch(value):
        return _result(True, "resend_api_key", "high", "Resend API key prefix matched")
    if LINEAR_API_KEY_RE.fullmatch(value):
        return _result(True, "linear_api_key", "high", "Linear API key prefix matched")
    if NOTION_TOKEN_RE.fullmatch(value):
        return _result(True, "notion_token", "high", "Notion integration token prefix matched")
    if RENDER_API_KEY_RE.fullmatch(value):
        return _result(True, "render_api_key", "high", "Render API key prefix matched")
    if LEMON_SQUEEZY_KEY_RE.fullmatch(value):
        return _result(True, "lemon_squeezy_api_key", "high", "Lemon Squeezy API key prefix matched")
    if RAILWAY_TOKEN_RE.fullmatch(value):
        return _result(True, "railway_token", "high", "Railway token prefix matched")
    if JWT_RE.fullmatch(value):
        if SUPABASE_KEY_NAMES.search(key) or "service_role" in lowered_key:
            return _result(True, "supabase_service_role_key", "high", "Supabase service role JWT matched")
        return _result(True, "jwt_token", "high", "JWT structure matched")

    if CLOUDFLARE_KEY_NAMES.search(key) and len(value) >= 32 and looks_random(value):
        return _result(True, "cloudflare_api_token", "high", "Cloudflare API token key with high-entropy value")

    if VERCEL_KEY_NAMES.search(key) and len(value) >= 24 and looks_random(value):
        return _result(True, "vercel_token", "high", "Vercel token key with high-entropy value")

    if RAILWAY_KEY_NAMES.search(key) and len(value) >= 20 and looks_random(value):
        return _result(True, "railway_token", "medium", "Railway credential key with non-placeholder value")
    if RENDER_KEY_NAMES.search(key) and len(value) >= 20 and looks_random(value):
        return _result(True, "render_api_key", "medium", "Render credential key with non-placeholder value")
    if LINEAR_KEY_NAMES.search(key) and len(value) >= 20 and looks_random(value):
        return _result(True, "linear_api_key", "medium", "Linear credential key with non-placeholder value")
    if NOTION_KEY_NAMES.search(key) and len(value) >= 20 and looks_random(value):
        return _result(True, "notion_token", "medium", "Notion credential key with non-placeholder value")
    if RESEND_KEY_NAMES.search(key) and len(value) >= 20 and looks_random(value):
        return _result(True, "resend_api_key", "medium", "Resend credential key with non-placeholder value")
    if LOOPS_KEY_NAMES.search(key) and len(value) >= 20 and looks_random(value):
        return _result(True, "loops_api_key", "medium", "Loops credential key with non-placeholder value")
    if LEMON_KEY_NAMES.search(key) and len(value) >= 20 and looks_random(value):
        return _result(True, "lemon_squeezy_api_key", "medium", "Lemon Squeezy credential key with non-placeholder value")
    if PLANETSCALE_KEY_NAMES.search(key):
        planet_db = _validate_database_url(value)
        if planet_db is not None:
            return planet_db
        if len(value) >= 16 and looks_random(value):
            return _result(True, "planetscale_credential", "high", "PlanetScale credential matched")

    return None


def _validate_infra_source(candidate: ExtractedSecret, value: str, key: str) -> ValidationResult | None:
    if candidate.source == "kubernetes_secret":
        if _contains_sensitive_key(key) and len(value) >= 8:
            entropy_label, _, entropy_reason = entropy_confidence(value)
            if entropy_label in {"medium", "high"}:
                return _result(
                    True,
                    "kubernetes_secret",
                    "high" if entropy_label == "high" else "medium",
                    f"Kubernetes secret value ({entropy_reason})",
                )
        return None
    if candidate.source in {"dockerfile_env", "cicd_env"}:
        prefix_result = _validate_by_prefix(value, key)
        if prefix_result and prefix_result.get("is_valid_candidate"):
            secret_type = str(prefix_result.get("secret_type") or "generic_secret")
            mapped = "dockerfile_secret" if candidate.source == "dockerfile_env" else "cicd_secret"
            if secret_type in {"database_url", "generic_secret", "credential_value", "high_entropy_secret"}:
                return _result(
                    True,
                    mapped,
                    str(prefix_result.get("confidence") or "medium"),
                    str(prefix_result.get("reason") or ""),
                )
            return _result(
                True,
                mapped,
                str(prefix_result.get("confidence") or "high"),
                str(prefix_result.get("reason") or ""),
            )
        db_result = _validate_database_url(value)
        if db_result and db_result.get("is_valid_candidate"):
            mapped = "dockerfile_secret" if candidate.source == "dockerfile_env" else "cicd_secret"
            return _result(True, mapped, "high", "infrastructure file database credential")
        if _contains_sensitive_key(key) and len(value) >= 12 and looks_random(value):
            mapped = "dockerfile_secret" if candidate.source == "dockerfile_env" else "cicd_secret"
            return _result(True, mapped, "medium", f"{candidate.source} sensitive assignment")
    return None


def validate_candidate(candidate: ExtractedSecret) -> ValidationResult:
    key = candidate.key or ""
    value = normalize_secret_value(candidate.value)
    lowered_key = key.lower()

    is_placeholder, placeholder_reason = is_placeholder_value(value)
    if is_placeholder and candidate.source != "private_key":
        return _result(False, "placeholder", "low", placeholder_reason)

    db_result = _validate_database_url(value)
    if db_result is not None:
        return db_result

    if PRIVATE_KEY_RE.search(value) or candidate.source == "private_key":
        return _result(True, "private_key", "high", "private key block marker found")

    infra_result = _validate_infra_source(candidate, value, key)
    if infra_result is not None:
        return infra_result

    prefix_result = _validate_by_prefix(value, key)
    if prefix_result is not None:
        return prefix_result

    if ("twilio" in lowered_key and "token" in lowered_key) and re.fullmatch(r"^[a-fA-F0-9]{32}$", value):
        return _result(True, "twilio_auth_token", "high", "Twilio auth token is a 32-character hex value")

    if "secret" in lowered_key and len(value) >= 24 and looks_random(value):
        return _result(True, "high_entropy_secret", "high", "secret-like key with high entropy value")

    if _contains_sensitive_key(key):
        entropy_label, _, entropy_reason = entropy_confidence(value)
        if entropy_label in {"medium", "high"}:
            return _result(
                True,
                "generic_secret",
                "high" if entropy_label == "high" else "medium",
                f"sensitive key with {entropy_reason}",
            )
        if len(value) >= 12 and not re.search(r"\s", value):
            return _result(
                True,
                "credential_value",
                "medium",
                f"sensitive key with non-placeholder value (entropy {shannon_entropy(value):.2f})",
            )
        return _result(False, "credential_value", "low", entropy_reason)

    if len(value) >= 24 and looks_random(value):
        return _result(True, "high_entropy_value", "medium", "unlabeled high entropy value")

    return _result(False, "unknown", "low", "no supported secret pattern matched")
