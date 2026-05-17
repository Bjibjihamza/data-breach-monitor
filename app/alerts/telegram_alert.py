from __future__ import annotations

import logging

import requests

from app.config import settings


logger = logging.getLogger(__name__)


def _detection_hash(detection: dict[str, object]) -> str:
    return str(detection.get("detection_hash") or "").strip()


def _already_sent(channel: str, detection_hash: str) -> bool:
    if not detection_hash:
        return False
    try:
        from app.storage.elastic_client import get_collection_state

        state = get_collection_state("alerts", f"{channel}:{detection_hash}")
    except Exception as exc:
        logger.warning("Unable to read alert state for %s/%s: %s", channel, detection_hash, exc.__class__.__name__)
        return False
    return bool(state.get("sent"))


def _mark_sent(channel: str, detection_hash: str) -> None:
    if not detection_hash:
        return
    try:
        from app.storage.elastic_client import update_collection_state

        update_collection_state("alerts", f"{channel}:{detection_hash}", {"sent": True})
    except Exception as exc:
        logger.warning("Unable to persist alert state for %s/%s: %s", channel, detection_hash, exc.__class__.__name__)


def _alert_text(detection: dict[str, object]) -> str:
    title = str(detection.get("title") or detection.get("summary") or "High severity detection")
    source = str(detection.get("source") or "unknown")
    severity = str(detection.get("severity") or "unknown")
    score = str(detection.get("risk_score") or "")
    affected_entity = str(detection.get("organization") or "unknown")
    url = str(detection.get("source_url") or detection.get("message_url") or "")
    lines = [
        "DBM high-severity detection",
        f"Source: {source}",
        f"Severity: {severity}",
        f"Risk score: {score or 'unknown'}",
        f"Affected entity: {affected_entity}",
        f"Title: {title[:500]}",
    ]
    if url:
        lines.append(f"Original: {url}")
    return "\n".join(lines)


def send_telegram_alert(detection: dict[str, object]) -> bool:
    detection_hash = _detection_hash(detection)
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        logger.info("Telegram alert skipped for %s: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing.", detection_hash or "unknown")
        return False

    if _already_sent("telegram", detection_hash):
        logger.info("Telegram alert already sent for detection %s; skipping duplicate.", detection_hash)
        return False

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "text": _alert_text(detection),
        "disable_web_page_preview": True,
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Telegram alert failed for detection %s: %s", detection_hash or "unknown", exc)
        return False

    _mark_sent("telegram", detection_hash)
    logger.info("Telegram alert sent for detection %s.", detection_hash or "unknown")
    return True
