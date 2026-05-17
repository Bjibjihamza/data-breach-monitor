from __future__ import annotations

from dataclasses import dataclass

from app.detection.policy import DetectionPolicy, load_detection_policy


CONFIDENCE_POINTS = {"low": 30, "medium": 60, "high": 90}
HIGH_VALUE_TYPES = {
    "github_token",
    "aws_access_key",
    "aws_secret_key",
    "stripe_live_secret_key",
    "slack_token",
    "twilio_auth_token",
    "jwt_token",
    "private_key",
    "database_url",
}


@dataclass(frozen=True)
class DetectionDecision:
    final_decision: str
    severity: str
    confidence: str
    confidence_score: int
    risk_score: int
    is_noise: bool
    noise_reason: str


def _max_confidence(validations: list[dict[str, bool | str]]) -> str:
    rank = {"low": 0, "medium": 1, "high": 2}
    confidence = "low"
    for validation in validations:
        candidate = str(validation.get("confidence") or "low")
        if rank.get(candidate, 0) > rank[confidence]:
            confidence = candidate
    return confidence


def _severity(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 40:
        return "medium"
    if score > 0:
        return "low"
    return "informational"


def score_validated_detection(
    *,
    file_path: str,
    is_example_path: bool,
    extracted_count: int,
    placeholder_count: int,
    validations: list[dict[str, bool | str]],
    has_sensitive_keywords: bool,
    has_suspicious_path: bool,
    has_domains: bool,
    has_watchlist: bool,
    policy: DetectionPolicy | None = None,
) -> DetectionDecision:
    policy = policy or load_detection_policy()
    validated_count = len(validations)

    if validated_count == 0:
        if extracted_count > 0 and placeholder_count == extracted_count and policy.ignore_placeholder_only:
            return DetectionDecision(
                final_decision="ignore",
                severity="informational",
                confidence="low",
                confidence_score=0,
                risk_score=0,
                is_noise=True,
                noise_reason="only placeholder or empty credential values",
            )
        if is_example_path and placeholder_count > 0 and policy.ignore_placeholder_only:
            return DetectionDecision(
                final_decision="ignore",
                severity="informational",
                confidence="low",
                confidence_score=0,
                risk_score=0,
                is_noise=True,
                noise_reason="example/documentation file with only placeholder values",
            )
        if has_sensitive_keywords or has_suspicious_path:
            score = 20 if has_sensitive_keywords or has_suspicious_path else 10
            final_decision = "low_signal" if policy.index_low_signals else "ignore"
            return DetectionDecision(
                final_decision=final_decision,
                severity="low",
                confidence="low",
                confidence_score=20,
                risk_score=score,
                is_noise=final_decision == "ignore",
                noise_reason="sensitive keywords or paths without validated secret values",
            )
        if has_domains:
            return DetectionDecision(
                final_decision="ignore",
                severity="informational",
                confidence="low",
                confidence_score=0,
                risk_score=0,
                is_noise=True,
                noise_reason="domain-only signal without validated secret values",
            )
        return DetectionDecision(
            final_decision="ignore",
            severity="informational",
            confidence="low",
            confidence_score=0,
            risk_score=0,
            is_noise=True,
            noise_reason="no actionable exposure signal",
        )

    secret_types = {str(validation.get("secret_type") or "") for validation in validations}
    confidence = _max_confidence(validations)
    confidence_score = CONFIDENCE_POINTS[confidence]
    score = 45

    if secret_types & HIGH_VALUE_TYPES:
        score = 80
    elif confidence == "high":
        score = 75
    elif confidence == "medium":
        score = 55

    if has_watchlist:
        score += 8
    if has_suspicious_path:
        score += 5
    if len(validations) > 1:
        score += min(10, (len(validations) - 1) * 3)

    if is_example_path and policy.example_paths_lower_confidence:
        if secret_types & HIGH_VALUE_TYPES:
            score -= 10
            confidence_score = min(confidence_score, 80)
        else:
            score -= 20
            confidence = "medium" if confidence == "high" else confidence
            confidence_score = min(confidence_score, CONFIDENCE_POINTS[confidence])

    score = max(0, min(100, score))
    if score < policy.min_risk_score_to_index:
        return DetectionDecision(
            final_decision="low_signal",
            severity=_severity(score),
            confidence=confidence,
            confidence_score=confidence_score,
            risk_score=score,
            is_noise=False,
            noise_reason="below configured indexing threshold",
        )

    return DetectionDecision(
        final_decision="index",
        severity=_severity(score),
        confidence=confidence,
        confidence_score=confidence_score,
        risk_score=score,
        is_noise=False,
        noise_reason="",
    )
