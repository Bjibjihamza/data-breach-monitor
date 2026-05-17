from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any


TELEGRAM_SOURCE = "telegram"
TELEGRAM_SIGNAL_TYPE = "telegram_public_channel_message"

CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
KEYWORD_PATTERNS: dict[str, tuple[str, ...]] = {
    "critical": ("critical",),
    "high severity": ("high severity",),
    "RCE": ("rce", "remote code execution"),
    "zero-day": ("zero-day", "0day", "zero day"),
    "exploit": ("exploit", "actively exploited"),
    "PoC": ("poc", "proof of concept"),
    "patch": ("patch", "patched", "fix available"),
    "vulnerability": ("vulnerability", "vulnerabilities"),
    "actively exploited": ("actively exploited", "exploited in the wild"),
    "CVSS": ("cvss",),
}
STRONG_KEYWORDS = {
    "critical",
    "high severity",
    "RCE",
    "zero-day",
    "actively exploited",
}
EXPLOIT_KEYWORDS = {"exploit", "PoC"}


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _contains_keyword(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    for pattern in patterns:
        normalized = pattern.casefold()
        if normalized.isalnum() or normalized in {"rce", "poc", "cvss", "0day"}:
            if re.search(rf"\b{re.escape(normalized)}\b", lowered):
                return True
        elif normalized in lowered:
            return True
    return False


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def analyze_telegram_message(text: str) -> dict[str, Any]:
    cve_ids = _unique([match.upper() for match in CVE_RE.findall(text)])
    detected_keywords = [
        label
        for label, patterns in KEYWORD_PATTERNS.items()
        if _contains_keyword(text, patterns)
    ]
    keyword_set = set(detected_keywords)

    if cve_ids:
        intel_category = "cve"
    elif keyword_set & EXPLOIT_KEYWORDS:
        intel_category = "exploit"
    elif detected_keywords:
        intel_category = "vulnerability_news"
    else:
        intel_category = "unknown"

    return {
        "cve_ids": cve_ids,
        "detected_keywords": detected_keywords,
        "intel_category": intel_category,
    }


def score_telegram_message(analysis: dict[str, Any]) -> dict[str, Any]:
    cve_ids = analysis.get("cve_ids") or []
    detected_keywords = analysis.get("detected_keywords") or []
    keyword_set = set(detected_keywords)
    has_cve = bool(cve_ids)
    has_exploit = bool(keyword_set & EXPLOIT_KEYWORDS)
    has_strong = bool(keyword_set & STRONG_KEYWORDS)

    if not has_cve and not detected_keywords:
        score = 10
        severity = "low"
        confidence = "low"
    elif has_cve and has_strong:
        score = 70
        severity = "high"
        confidence = "medium"
    elif has_cve and has_exploit:
        score = 50
        severity = "medium"
        confidence = "medium"
    elif has_cve:
        score = 30
        severity = "low"
        confidence = "medium"
    else:
        score = 20
        severity = "low"
        confidence = "low"

    strong_keyword_count = len(keyword_set & (STRONG_KEYWORDS | EXPLOIT_KEYWORDS))
    if strong_keyword_count > 1:
        score += min(10, (strong_keyword_count - 1) * 5)

    score = min(score, 80)
    if score >= 70 and has_cve and has_strong:
        severity = "high"
    elif score >= 50:
        severity = "medium"

    return {
        "risk_score": score,
        "severity": severity,
        "confidence": confidence,
    }


def telegram_detection_hash(channel_username: str, message_id: int | str) -> str:
    hash_input = f"telegram:{channel_username}:{message_id}"
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def normalize_telegram_detection(raw_event: dict[str, Any]) -> dict[str, Any]:
    text = _as_text(raw_event.get("text") or raw_event.get("raw_text"))
    channel_username = _as_text(raw_event.get("channel_username")).lstrip("@")
    message_id = raw_event.get("message_id") or 0
    analysis = analyze_telegram_message(text)
    scoring = score_telegram_message(analysis)

    detection: dict[str, Any] = {
        "source": TELEGRAM_SOURCE,
        "signal_type": TELEGRAM_SIGNAL_TYPE,
        "channel_name": _as_text(raw_event.get("channel_name")),
        "channel_username": channel_username,
        "channel_url": _as_text(raw_event.get("channel_url")),
        "message_id": int(message_id),
        "message_url": _as_text(raw_event.get("message_url")),
        "source_url": _as_text(raw_event.get("message_url")),
        "title": f"{_as_text(raw_event.get('channel_name')) or channel_username}: message {message_id}",
        "text": text,
        "summary": text[:500],
        "redacted_text": text,
        "published_at": _as_text(raw_event.get("published_at")),
        "collected_at": _as_text(raw_event.get("collected_at")),
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "category": _as_text(raw_event.get("category")),
        "risk_category": _as_text(raw_event.get("category")),
        "source_type": _as_text(raw_event.get("source_type")) or "telegram_public_channel",
        "requires_validation": True,
        "status": "new",
        "triage_status": "new",
        "cve_ids": analysis["cve_ids"],
        "detected_keywords": analysis["detected_keywords"],
        "intel_category": analysis["intel_category"],
        "detected_indicators": analysis["detected_keywords"],
        "confidence": scoring["confidence"],
        "severity": scoring["severity"],
        "risk_score": scoring["risk_score"],
        "confidence_score": scoring["risk_score"],
        "detection_category": TELEGRAM_SIGNAL_TYPE,
        "final_decision": "requires_validation",
        "organization": "",
        "matched_watchlist": [],
        "matched_domains": [],
        "matched_emails": [],
        "secret_types": [],
        "validation_reasons": [],
        "is_noise": False,
        "noise_reason": "",
        "extracted_secrets_count": 0,
        "validated_secrets_count": 0,
        "placeholder_count": 0,
        "content_evidence": analysis["detected_keywords"],
        "evidence_lines": [text] if text else [],
        "evidence_line_numbers": [],
        "evidence_excerpt": text[:500],
        "search_query_context": channel_username,
        "text_length": len(text),
    }
    detection["detection_hash"] = telegram_detection_hash(channel_username, message_id)
    return detection
