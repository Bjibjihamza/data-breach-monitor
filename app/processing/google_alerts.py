from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


PUBLIC_BREACH_NEWS = "public_breach_news"
GOOGLE_ALERTS_SOURCE = "google_alerts"

STRONG_BREACH_PATTERNS = (
    "data breach",
    "credentials leaked",
    "password dump",
    "database dump",
    "ransomware",
    "dark web",
    "exposed data",
    "customer data exposed",
    "database exposed",
    "token leaked",
    "api key exposed",
    "fuite de données",
    "donnees exposees",
    "données exposées",
)
WEAK_BREACH_PATTERNS = (
    "breach",
    "leak",
    "leaked",
    "credentials",
    "dump",
    "fuite",
    "cyberattaque",
    "piratage",
)
CREDENTIAL_DUMP_PATTERNS = (
    "credentials leaked",
    "password dump",
    "database dump",
    "combo list",
    "token leaked",
    "api key exposed",
    "database exposed",
)
TRUSTED_SOURCE_HINTS = (
    "bleepingcomputer",
    "therecord.media",
    "securityweek",
    "darkreading",
    "cybernews",
    "thehackernews",
    "krebsonsecurity",
    "techcrunch",
    "reuters",
    "apnews",
    "bbc.",
    "cnn.",
    "lemonde.",
    "hespress",
    "medias24",
    "moroccoworldnews",
)
LOW_TRUST_SOURCE_HINTS = (
    "blogspot.",
    "wordpress.",
    "medium.com",
    "substack.com",
    "pastebin.",
)


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_as_text(item) for item in value if _as_text(item)]
    return []


def _normalize_for_matching(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_text = _normalize_for_matching(text)
    normalized_phrase = _normalize_for_matching(phrase)
    if len(normalized_phrase) <= 4 and normalized_phrase.isalnum():
        return bool(re.search(rf"\b{re.escape(normalized_phrase)}\b", normalized_text))
    return normalized_phrase in normalized_text


def _matched_patterns(text: str, patterns: tuple[str, ...]) -> list[str]:
    return [pattern for pattern in patterns if _contains_phrase(text, pattern)]


def _matched_organizations(text: str, organizations: list[str]) -> list[str]:
    return [organization for organization in organizations if _contains_phrase(text, organization)]


def _source_host(source_url: str) -> str:
    host = urlparse(source_url).netloc.lower()
    if host.startswith("www."):
        return host[4:]
    return host


def _source_reputation(source_url: str, source_name: str) -> str:
    haystack = f"{_source_host(source_url)} {_normalize_for_matching(source_name)}"
    if any(hint in haystack for hint in TRUSTED_SOURCE_HINTS):
        return "trusted"
    if any(hint in haystack for hint in LOW_TRUST_SOURCE_HINTS):
        return "low_trust"
    return "unknown"


def _days_old(published_at: str) -> int | None:
    if not published_at:
        return None
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - published).days)


def _score_google_alert(
    *,
    text: str,
    source_url: str,
    source_name: str,
    matched_organizations: list[str],
    published_at: str,
) -> dict[str, Any]:
    strong_matches = _matched_patterns(text, STRONG_BREACH_PATTERNS)
    weak_matches = _matched_patterns(text, WEAK_BREACH_PATTERNS)
    credential_matches = _matched_patterns(text, CREDENTIAL_DUMP_PATTERNS)
    reputation = _source_reputation(source_url, source_name)
    days_old = _days_old(published_at)

    score = 10
    if matched_organizations:
        score += 15
    else:
        score -= 10

    if weak_matches:
        score += 10
    if strong_matches:
        score += 25
    if credential_matches:
        score += 15

    if reputation == "trusted":
        score += 10
    elif reputation == "low_trust":
        score -= 10

    if days_old is not None:
        if days_old > 365:
            score -= 20
        elif days_old > 180:
            score -= 10
        elif days_old > 90:
            score -= 5

    if not matched_organizations:
        score = min(score, 35)
    if not strong_matches and not credential_matches:
        score = min(score, 45 if weak_matches else 30)

    score = max(0, min(100, score))
    severity = "low"
    confidence = "low"

    if (
        score >= 70
        and matched_organizations
        and strong_matches
        and reputation == "trusted"
    ):
        severity = "high"
        confidence = "high"
    elif score >= 35 and matched_organizations and weak_matches:
        severity = "medium"
        confidence = "medium"
    elif score >= 40 and (strong_matches or credential_matches or matched_organizations):
        severity = "medium"
        confidence = "medium" if matched_organizations else "low"

    return {
        "risk_score": score,
        "severity": severity,
        "confidence": confidence,
        "matched_keywords": list(dict.fromkeys(strong_matches + weak_matches + credential_matches)),
        "source_reputation": reputation,
        "article_age_days": days_old,
    }


def google_alert_detection_hash(detection: dict[str, Any]) -> str:
    hash_input = "|".join(
        [
            _as_text(detection.get("source")),
            _as_text(detection.get("alert_name")),
            _as_text(detection.get("source_url")),
            _as_text(detection.get("title")),
        ]
    )
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def normalize_google_alert_detection(raw_event: dict[str, Any]) -> dict[str, Any]:
    organizations = _as_text_list(raw_event.get("organizations"))
    title = _as_text(raw_event.get("title"))
    summary = _as_text(raw_event.get("summary"))
    text = f"{title}\n{summary}".strip()
    matched_organizations = _matched_organizations(text, organizations)
    matched_organization = matched_organizations[0] if len(matched_organizations) == 1 else None
    published_at = _as_text(raw_event.get("published_at"))
    source_url = _as_text(raw_event.get("source_url"))
    source_name = _as_text(raw_event.get("source_name"))
    scoring = _score_google_alert(
        text=text,
        source_url=source_url,
        source_name=source_name,
        matched_organizations=matched_organizations,
        published_at=published_at,
    )

    if matched_organization:
        organization = matched_organization
    elif len(matched_organizations) > 1:
        organization = ", ".join(matched_organizations)
    else:
        organization = ""

    detection: dict[str, Any] = {
        "source": GOOGLE_ALERTS_SOURCE,
        "signal_type": PUBLIC_BREACH_NEWS,
        "alert_name": _as_text(raw_event.get("alert_name")),
        "category": _as_text(raw_event.get("category")),
        "country": _as_text(raw_event.get("country")),
        "organizations": organizations,
        "matched_organization": matched_organization,
        "matched_organizations": matched_organizations,
        "query": _as_text(raw_event.get("query")),
        "title": title,
        "summary": summary,
        "source_url": source_url,
        "source_name": source_name,
        "published_at": published_at,
        "collected_at": _as_text(raw_event.get("collected_at")),
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "requires_validation": True,
        "status": "new",
        "triage_status": "new",
        "organization": organization,
        "risk_category": _as_text(raw_event.get("category")),
        "confidence": scoring["confidence"],
        "severity": scoring["severity"],
        "risk_score": scoring["risk_score"],
        "detection_category": PUBLIC_BREACH_NEWS,
        "final_decision": "requires_validation",
        "detected_indicators": ["public_report"],
        "matched_watchlist": matched_organizations,
        "matched_domains": [],
        "matched_emails": [],
        "secret_types": [],
        "validation_reasons": [],
        "is_noise": False,
        "noise_reason": "",
        "extracted_secrets_count": 0,
        "validated_secrets_count": 0,
        "placeholder_count": 0,
        "confidence_score": scoring["risk_score"],
        "content_evidence": scoring["matched_keywords"],
        "evidence_lines": [line for line in (title, summary) if line],
        "evidence_line_numbers": [],
        "evidence_excerpt": summary[:500],
        "search_query_context": _as_text(raw_event.get("query")),
        "redacted_text": text,
        "text_length": len(text),
        "source_reputation": scoring["source_reputation"],
        "article_age_days": scoring["article_age_days"],
    }
    detection["detection_hash"] = google_alert_detection_hash(detection)
    return detection
