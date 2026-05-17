from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

from app.detection.entropy import entropy_confidence, looks_random, shannon_entropy
from app.detection.extractors import ExtractedSecret
from app.detection.noise import is_placeholder_value, normalize_secret_value


Confidence = Literal["low", "medium", "high"]
ValidationResult = dict[str, bool | str]

GITHUB_TOKEN_RE = re.compile(
    r"^(?:gh[oprsu]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{20,}_[A-Za-z0-9_]{20,})$"
)
AWS_ACCESS_KEY_RE = re.compile(r"^(?:AKIA|ASIA)[A-Z0-9]{16}$")
AWS_SECRET_RE = re.compile(r"^[A-Za-z0-9/+=]{40}$")
STRIPE_LIVE_SECRET_RE = re.compile(r"^sk_live_[A-Za-z0-9]{16,}$")
SLACK_TOKEN_RE = re.compile(r"^xox[abprs]-[A-Za-z0-9-]{10,}$")
TWILIO_AUTH_TOKEN_RE = re.compile(r"^[a-fA-F0-9]{32}$")
JWT_RE = re.compile(r"^eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}$")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+)?PRIVATE KEY-----", re.IGNORECASE)

SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|secret|token|password|passwd|pwd|credential|private[_-]?key|client[_-]?secret)",
    re.IGNORECASE,
)
DATABASE_SCHEMES = {"postgres", "postgresql", "mysql", "mongodb", "mongodb+srv", "redis", "mariadb"}


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
    return _result(True, "database_url", "high", "database URL contains username, password, and host")


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

    if GITHUB_TOKEN_RE.fullmatch(value):
        return _result(True, "github_token", "high", "GitHub token prefix and length matched")

    if AWS_ACCESS_KEY_RE.fullmatch(value):
        return _result(True, "aws_access_key", "high", "AWS access key id format matched")

    if "aws_secret_access_key" in lowered_key and AWS_SECRET_RE.fullmatch(value):
        return _result(True, "aws_secret_key", "high", "AWS secret access key format matched")

    if STRIPE_LIVE_SECRET_RE.fullmatch(value):
        return _result(True, "stripe_live_secret_key", "high", "Stripe live secret key prefix matched")

    if SLACK_TOKEN_RE.fullmatch(value):
        return _result(True, "slack_token", "high", "Slack token prefix matched")

    if ("twilio" in lowered_key and "token" in lowered_key) and TWILIO_AUTH_TOKEN_RE.fullmatch(value):
        return _result(True, "twilio_auth_token", "high", "Twilio auth token is a 32-character hex value")

    if JWT_RE.fullmatch(value):
        return _result(True, "jwt_token", "high", "JWT structure matched")

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

