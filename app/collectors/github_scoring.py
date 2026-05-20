from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.detection.noise import classify_github_path, is_github_weak_template_path, is_placeholder_value
from app.detection.scoring import HIGH_VALUE_TYPES
from app.detection.validators import PRIVATE_KEY_RE, validate_candidate
from app.detection.extractors import ExtractedSecret, extract_secret_candidates
from app.processing.detector import (
    AWS_ACCESS_KEY_RE as CONTENT_AWS_RE,
    GITHUB_TOKEN_RE as CONTENT_GH_RE,
    JWT_RE as CONTENT_JWT_RE,
    OPENAI_KEY_RE,
    PASSWORD_ASSIGNMENT_RE,
    PRIVATE_KEY_RE as CONTENT_PRIVATE_KEY_RE,
    extract_content_evidence,
)

# GitHub indexing threshold: settings.GITHUB_MIN_RISK_SCORE_TO_INDEX (app/config.py).
# detection_policy.yml min_risk_score_to_index applies to the generic pipeline only.

EMPTY_ASSIGNMENT_RE = re.compile(
    r"\b(?:DB_PASSWORD|DATABASE_URL|PASSWORD|SECRET|API_KEY|SECRET_KEY)\b\s*[:=]\s*(?:''|\"\"|)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

DB_URI_WITH_CREDS_RE = re.compile(
    r"\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|mariadb)://[^:]+:[^@\s]+@[^\s'\"<>]+",
    re.IGNORECASE,
)

OPENAI_SK_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")
SUPABASE_SERVICE_ROLE_RE = re.compile(
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
)
OAUTH_CLIENT_SECRET_RE = re.compile(
    r"\b(?:client_secret|oauth_secret)\b\s*[:=]\s*[\"']?[A-Za-z0-9._~+/=-]{16,}[\"']?",
    re.IGNORECASE,
)
SMTP_PASSWORD_RE = re.compile(
    r"\b(?:smtp_password|mail_password|email_password)\b\s*[:=]\s*[\"']?[^\s\"']{6,}[\"']?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GitHubScoringResult:
    path_classification: str
    evidence_strength: str
    scoring_reason: str
    risk_score: int
    severity: str
    should_index: bool
    should_export: bool
    drop_reason: str
    downgraded_template: bool
    skipped_placeholder: bool
    skipped_low_confidence: bool


def _counts(indicators: dict[str, Any]) -> tuple[int, int, int]:
    try:
        extracted = int(indicators.get("extracted_secrets_count") or 0)
    except (TypeError, ValueError):
        extracted = 0
    try:
        placeholder = int(indicators.get("placeholder_count") or 0)
    except (TypeError, ValueError):
        placeholder = 0
    try:
        validated = int(indicators.get("validated_secrets_count") or 0)
    except (TypeError, ValueError):
        validated = 0
    return extracted, placeholder, validated


def _is_placeholder_only(indicators: dict[str, Any]) -> bool:
    extracted, placeholder, validated = _counts(indicators)
    if validated > 0:
        return False
    if extracted > 0 and placeholder >= extracted:
        return True
    return False


def _is_suspicious_path_only(
    indicators: dict[str, Any],
    content: str,
    file_path: str,
) -> bool:
    _, _, validated = _counts(indicators)
    if validated > 0:
        return False
    content_evidence = list(indicators.get("content_evidence") or extract_content_evidence(content, file_path))
    if not content_evidence:
        return False
    return all(label.startswith("suspicious_path:") for label in content_evidence)


def _has_strong_pattern_in_content(content: str) -> tuple[bool, list[str]]:
    signals: list[str] = []
    if CONTENT_PRIVATE_KEY_RE.search(content) or PRIVATE_KEY_RE.search(content):
        signals.append("private_key_block")
    if CONTENT_AWS_RE.search(content):
        signals.append("aws_access_key")
    if CONTENT_GH_RE.search(content):
        signals.append("github_token")
    if OPENAI_KEY_RE.search(content) or OPENAI_SK_RE.search(content):
        signals.append("openai_api_key")
    if CONTENT_JWT_RE.search(content) or SUPABASE_SERVICE_ROLE_RE.search(content):
        signals.append("jwt_token")
    if DB_URI_WITH_CREDS_RE.search(content):
        signals.append("database_uri_with_credentials")
    if OAUTH_CLIENT_SECRET_RE.search(content):
        signals.append("oauth_client_secret")
    if SMTP_PASSWORD_RE.search(content):
        signals.append("smtp_password")
    return bool(signals), signals


def _assignment_has_real_value(content: str) -> bool:
    for match in PASSWORD_ASSIGNMENT_RE.finditer(content):
        fragment = match.group(0)
        value = fragment.split("=", 1)[-1].split(":", 1)[-1].strip().strip("'\"")
        if value and not is_placeholder_value(value)[0]:
            return True
    for candidate in extract_secret_candidates(content):
        if not candidate.key:
            continue
        if not candidate.value:
            continue
        if is_placeholder_value(candidate.value)[0]:
            continue
        lowered = candidate.key.lower()
        if any(token in lowered for token in ("password", "secret", "token", "key", "credential")):
            return True
    return False


def _validated_secret_types(indicators: dict[str, Any]) -> set[str]:
    secret_types = indicators.get("secret_types")
    if isinstance(secret_types, list):
        return {str(item) for item in secret_types if item}
    return set()


def _candidate_is_secretish(candidate: ExtractedSecret) -> bool:
    lowered = (candidate.key or "").lower()
    if candidate.source == "private_key":
        return True
    return any(token in lowered for token in ("password", "secret", "token", "key", "credential", "aws"))


def _has_validated_strong_secret(indicators: dict[str, Any], content: str) -> bool:
    """Strong evidence requires at least one validated real secret (not regex-only)."""
    secret_types = _validated_secret_types(indicators)
    if secret_types & HIGH_VALUE_TYPES:
        return True

    _, _, validated_count = _counts(indicators)
    if validated_count <= 0:
        return False

    for candidate in extract_secret_candidates(content):
        if not _candidate_is_secretish(candidate):
            continue
        validation = validate_candidate(candidate)
        if not validation.get("is_valid_candidate"):
            continue
        secret_type = str(validation.get("secret_type") or "")
        confidence = str(validation.get("confidence") or "")
        if secret_type in HIGH_VALUE_TYPES or confidence == "high":
            return True
    return False


def _determine_evidence_strength(
    *,
    content: str,
    file_path: str,
    indicators: dict[str, Any],
    path_classification: str,
) -> tuple[str, str]:
    content_evidence = list(indicators.get("content_evidence") or extract_content_evidence(content, file_path))
    _, placeholder_count, validated_count = _counts(indicators)
    extracted_count, _, _ = _counts(indicators)

    if _has_validated_strong_secret(indicators, content):
        _, pattern_labels = _has_strong_pattern_in_content(content)
        reason = "validated strong secret"
        if pattern_labels:
            reason = f"validated strong secret ({', '.join(pattern_labels)})"
        return "strong", reason

    if validated_count > 0:
        return "medium", "validated credential value without high-confidence secret classification"

    if _assignment_has_real_value(content):
        return "medium", "credential assignment with non-placeholder value"

    if EMPTY_ASSIGNMENT_RE.search(content):
        return "weak", "empty credential assignment"

    if placeholder_count > 0 and extracted_count > 0 and placeholder_count >= extracted_count:
        return "weak", "only placeholder or empty credential values"

    weak_only_evidence = (
        all(
            label.startswith("suspicious_path:")
            or label in {"password=", "DB_PASSWORD", "API_KEY", "SECRET_KEY", "token="}
            for label in content_evidence
        )
        if content_evidence
        else True
    )

    if content_evidence and not weak_only_evidence:
        return "medium", "multiple credential indicators without confirmed real secret"

    if content_evidence or path_classification == "strong_suspicious":
        return "weak", "suspicious path or variable names without confirmed real secret"

    return "weak", "no actionable credential evidence"


def _severity_from_score(score: int) -> str:
    if score >= 80:
        return "high"
    if score >= 40:
        return "medium"
    if score > 0:
        return "low"
    return "informational"


def _base_score_for_strength(evidence_strength: str) -> tuple[int, str]:
    if evidence_strength == "strong":
        return 85, "high"
    if evidence_strength == "medium":
        return 52, "medium"
    return 22, "low"


def _build_drop_result(
    *,
    path_classification: str,
    path_reason: str,
    evidence_strength: str,
    evidence_reason: str,
    drop_reason: str,
    downgraded_template: bool = False,
) -> GitHubScoringResult:
    scoring_reason = f"{path_reason}; {evidence_reason}"
    if downgraded_template:
        scoring_reason = f"Template/example path downgrade applied. {scoring_reason}"
    severity = "informational" if drop_reason == "placeholder_only" else "low"
    return GitHubScoringResult(
        path_classification=path_classification,
        evidence_strength=evidence_strength,
        scoring_reason=scoring_reason,
        risk_score=25,
        severity=severity,
        should_index=False,
        should_export=False,
        drop_reason=drop_reason,
        downgraded_template=downgraded_template,
        skipped_placeholder=drop_reason == "placeholder_only",
        skipped_low_confidence=True,
    )


def score_github_finding(
    content: str,
    file_path: str,
    indicators: dict[str, Any],
) -> GitHubScoringResult:
    path_classification, path_reason = classify_github_path(file_path)
    template_like = path_classification == "weak_template" or is_github_weak_template_path(file_path)

    if _is_placeholder_only(indicators):
        return _build_drop_result(
            path_classification=path_classification,
            path_reason=path_reason,
            evidence_strength="weak",
            evidence_reason="only placeholder or empty credential values",
            drop_reason="placeholder_only",
            downgraded_template=template_like,
        )

    if _is_suspicious_path_only(indicators, content, file_path):
        return _build_drop_result(
            path_classification=path_classification,
            path_reason=path_reason,
            evidence_strength="weak",
            evidence_reason="suspicious path only without validated secret",
            drop_reason="suspicious_path_only",
        )

    evidence_strength, evidence_reason = _determine_evidence_strength(
        content=content,
        file_path=file_path,
        indicators=indicators,
        path_classification=path_classification,
    )

    has_strong_validated = _has_validated_strong_secret(indicators, content)
    risk_score, severity = _base_score_for_strength(evidence_strength)
    downgraded_template = False
    drop_reason = ""

    if settings.GITHUB_DOWNGRADE_TEMPLATE_FILES and template_like and not has_strong_validated:
        downgraded_template = True
        if evidence_strength == "weak":
            return _build_drop_result(
                path_classification=path_classification,
                path_reason=path_reason,
                evidence_strength=evidence_strength,
                evidence_reason=evidence_reason,
                drop_reason="template_weak",
                downgraded_template=True,
            )
        if evidence_strength == "medium":
            risk_score = min(risk_score, settings.GITHUB_MIN_RISK_SCORE_TO_INDEX - 1)
            severity = _severity_from_score(risk_score)
            drop_reason = "template_weak"

    if settings.GITHUB_REQUIRE_STRONG_SECRET_FOR_HIGH:
        if severity == "high" and evidence_strength != "strong":
            risk_score = min(risk_score, 65)
            severity = "medium"
        if evidence_strength == "strong" and not has_strong_validated:
            risk_score = min(risk_score, 65)
            severity = "medium"
            evidence_strength = "medium"

    if path_classification == "strong_suspicious" and evidence_strength == "medium":
        risk_score = min(100, risk_score + 5)

    scoring_reason = f"{path_reason}; {evidence_reason}"
    if downgraded_template and drop_reason != "template_weak":
        scoring_reason = f"Template/example path downgrade applied. {scoring_reason}"
    elif downgraded_template:
        scoring_reason = f"Template/example path capped below GitHub index threshold. {scoring_reason}"

    risk_score = max(0, min(100, risk_score))
    severity = _severity_from_score(risk_score)

    min_risk = max(0, settings.GITHUB_MIN_RISK_SCORE_TO_INDEX)
    include_low = settings.GITHUB_INCLUDE_LOW_CONFIDENCE
    low_severities = {"informational", "low"}

    skipped_low_confidence = False
    should_index = True
    if risk_score < min_risk or severity in low_severities:
        if not include_low or risk_score < min_risk:
            should_index = False
            skipped_low_confidence = True
            if not drop_reason:
                _, _, validated = _counts(indicators)
                extracted, _, _ = _counts(indicators)
                if validated == 0 and extracted > 0:
                    drop_reason = "no_validated_secret"
                else:
                    drop_reason = "low_confidence"

    if evidence_strength == "weak" and not should_index and not drop_reason:
        drop_reason = "low_confidence"

    should_export = should_index
    if should_index and not settings.GITHUB_EXPORT_LOW_CONFIDENCE and severity in low_severities:
        should_export = False

    return GitHubScoringResult(
        path_classification=path_classification,
        evidence_strength=evidence_strength,
        scoring_reason=scoring_reason,
        risk_score=risk_score,
        severity=severity,
        should_index=should_index,
        should_export=should_export,
        drop_reason=drop_reason,
        downgraded_template=downgraded_template,
        skipped_placeholder=False,
        skipped_low_confidence=skipped_low_confidence,
    )


def apply_github_scoring_to_indicators(
    content: str,
    file_path: str,
    indicators: dict[str, Any],
) -> GitHubScoringResult:
    result = score_github_finding(content, file_path, indicators)
    indicators["path_classification"] = result.path_classification
    indicators["evidence_strength"] = result.evidence_strength
    indicators["scoring_reason"] = result.scoring_reason
    indicators["risk_score"] = result.risk_score
    indicators["severity"] = result.severity
    indicators["github_should_index"] = result.should_index
    indicators["github_should_export"] = result.should_export
    indicators["github_downgraded_template"] = result.downgraded_template
    indicators["github_skipped_placeholder"] = result.skipped_placeholder
    indicators["github_skipped_low_confidence"] = result.skipped_low_confidence
    indicators["drop_reason"] = result.drop_reason

    if not result.should_index:
        indicators["final_decision"] = "ignore"
        indicators["is_noise"] = True
        indicators["noise_reason"] = result.scoring_reason
    elif result.severity == "low" and not settings.GITHUB_INCLUDE_LOW_CONFIDENCE:
        indicators["final_decision"] = "low_signal"
        indicators["is_noise"] = False
    else:
        indicators["final_decision"] = "index"
        indicators["is_noise"] = False
        indicators["noise_reason"] = ""

    return result
