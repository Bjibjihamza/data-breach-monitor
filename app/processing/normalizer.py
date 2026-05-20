from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.processing.redactor import mask_email_value


def normalize_detection(
    raw_event: dict[str, Any],
    clean_text: str,
    indicators: dict[str, list[str]],
    redacted_text: str,
    score: int,
    severity: str,
    confidence: str,
) -> dict[str, object]:
    _meta_keys = {
        "matched_watchlist",
        "organization",
        "risk_category",
        "detection_category",
        "store_recommended",
        "suspicious_paths",
        "exposure_keywords",
        "public_contact_emails",
        "phones",
        "content_evidence",
        "evidence_lines",
        "evidence_line_numbers",
        "evidence_excerpt",
        "search_query_context",
        "is_example_path",
        "example_path_reason",
        "is_noise",
        "noise_reason",
        "extracted_secrets_count",
        "validated_secrets_count",
        "placeholder_count",
        "secret_types",
        "validation_reasons",
        "final_decision",
        "triage_status",
        "confidence_score",
        "path_classification",
        "evidence_strength",
        "scoring_reason",
        "github_should_index",
        "github_should_export",
        "github_downgraded_template",
        "github_skipped_placeholder",
        "github_skipped_low_confidence",
        "drop_reason",
        "rejected_unknown_format",
    }
    detected_indicators = [
        key
        for key, values in indicators.items()
        if key not in _meta_keys and values
    ]

    organization = str(
        indicators.get("organization") or raw_event.get("organization") or ""
    ).strip()
    event_metadata = raw_event.get("metadata") or {}
    risk_category = str(
        indicators.get("risk_category")
        or raw_event.get("risk_category")
        or event_metadata.get("risk_category")
        or ""
    ).strip()

    return {
        "source": raw_event.get("source", ""),
        "source_url": raw_event.get("source_url") or raw_event.get("url", ""),
        "title": raw_event.get("title", ""),
        "organization": organization,
        "risk_category": risk_category,
        "confidence": confidence,
        "collected_at": raw_event.get("collected_at") or raw_event.get("timestamp", ""),
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "matched_emails": [mask_email_value(email) for email in indicators.get("emails", [])],
        "matched_domains": indicators.get("domains", []),
        "matched_watchlist": indicators.get("matched_watchlist", []),
        "detected_indicators": detected_indicators,
        "redacted_text": redacted_text,
        "risk_score": score,
        "severity": severity,
        "detection_category": str(indicators.get("detection_category", "")),
        "content_evidence": list(indicators.get("content_evidence", [])),
        "evidence_lines": list(indicators.get("evidence_lines", [])),
        "evidence_line_numbers": list(indicators.get("evidence_line_numbers", [])),
        "evidence_excerpt": str(indicators.get("evidence_excerpt") or "")[:500],
        "path_classification": str(indicators.get("path_classification") or ""),
        "evidence_strength": str(indicators.get("evidence_strength") or ""),
        "scoring_reason": str(indicators.get("scoring_reason") or ""),
        "search_query_context": str(
            indicators.get("search_query_context")
            or event_metadata.get("search_query_context", "")
        ),
        "is_noise": bool(indicators.get("is_noise", False)),
        "noise_reason": str(indicators.get("noise_reason") or ""),
        "extracted_secrets_count": int(indicators.get("extracted_secrets_count") or 0),
        "validated_secrets_count": int(indicators.get("validated_secrets_count") or 0),
        "placeholder_count": int(indicators.get("placeholder_count") or 0),
        "secret_types": list(indicators.get("secret_types", [])),
        "validation_reasons": list(indicators.get("validation_reasons", [])),
        "final_decision": str(indicators.get("final_decision") or "index"),
        "triage_status": str(indicators.get("triage_status") or "new"),
        "confidence_score": int(indicators.get("confidence_score") or 0),
        "status": str(indicators.get("triage_status") or "new"),
        "text_length": len(clean_text),
    }
