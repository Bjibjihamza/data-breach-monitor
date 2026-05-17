from __future__ import annotations

from app.processing.categories import EXPOSURE_SIGNAL, INFORMATIONAL_MENTION, SECRET_EXPOSURE


def compute_confidence(indicators: dict[str, list[str] | str]) -> str:
    if indicators.get("confidence"):
        return str(indicators["confidence"])

    category = str(indicators.get("detection_category", INFORMATIONAL_MENTION))
    has_watchlist = bool(indicators.get("matched_watchlist"))

    if category == SECRET_EXPOSURE:
        return "high"
    if category == EXPOSURE_SIGNAL:
        if has_watchlist:
            return "high"
        if indicators.get("risk_category"):
            return "medium"
        return "medium"
    return "low"


def score_detection(raw_event: dict[str, str], indicators: dict[str, list[str] | str]) -> tuple[int, str]:
    if indicators.get("risk_score") is not None and indicators.get("severity"):
        try:
            return int(indicators.get("risk_score") or 0), str(indicators.get("severity"))
        except (TypeError, ValueError):
            pass

    category = str(indicators.get("detection_category", INFORMATIONAL_MENTION))
    has_watchlist = bool(indicators.get("matched_watchlist"))
    has_suspicious_path = bool(indicators.get("suspicious_paths"))

    if category == INFORMATIONAL_MENTION:
        return 0, "informational"

    if category == SECRET_EXPOSURE:
        score = 85
        if has_watchlist:
            score += 10
        return min(score, 100), "high"

    if category == EXPOSURE_SIGNAL:
        if has_watchlist and has_suspicious_path:
            return 50, "medium"
        if has_watchlist:
            return 45, "medium"
        return 40, "medium"

    return 0, "informational"
