from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

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


def _message_body(detection: dict[str, object]) -> str:
    title = str(detection.get("title") or detection.get("summary") or "High severity detection")
    source = str(detection.get("source") or "unknown")
    severity = str(detection.get("severity") or "unknown")
    score = str(detection.get("risk_score") or "unknown")
    affected_entity = str(detection.get("organization") or "unknown")
    url = str(detection.get("source_url") or detection.get("message_url") or "")
    evidence = str(detection.get("evidence_excerpt") or detection.get("redacted_text") or "")[:1200]
    lines = [
        "DBM high-severity detection",
        "",
        f"Source: {source}",
        f"Severity: {severity}",
        f"Risk score: {score}",
        f"Affected entity: {affected_entity}",
        f"Title: {title}",
    ]
    if url:
        lines.append(f"Original: {url}")
    if evidence:
        lines.extend(["", "Evidence:", evidence])
    return "\n".join(lines)


def send_email_alert(detection: dict[str, object]) -> bool:
    detection_hash = _detection_hash(detection)
    if not settings.SMTP_HOST or not settings.ALERT_EMAIL_TO:
        logger.info("Email alert skipped for %s: SMTP_HOST or ALERT_EMAIL_TO is missing.", detection_hash or "unknown")
        return False

    if _already_sent("email", detection_hash):
        logger.info("Email alert already sent for detection %s; skipping duplicate.", detection_hash)
        return False

    recipients = [item.strip() for item in settings.ALERT_EMAIL_TO.split(",") if item.strip()]
    if not recipients:
        logger.info("Email alert skipped for %s: ALERT_EMAIL_TO has no usable recipients.", detection_hash or "unknown")
        return False

    msg = EmailMessage()
    msg["Subject"] = f"DBM high-severity detection: {str(detection.get('source') or 'unknown')}"
    msg["From"] = settings.SMTP_USER or "data-breach-monitor@localhost"
    msg["To"] = ", ".join(recipients)
    msg.set_content(_message_body(detection))

    try:
        port = int(settings.SMTP_PORT or 587)
    except ValueError:
        port = 587

    try:
        with smtplib.SMTP(settings.SMTP_HOST, port, timeout=15) as client:
            client.ehlo()
            if port != 25:
                try:
                    client.starttls()
                    client.ehlo()
                except smtplib.SMTPException as exc:
                    logger.warning("SMTP STARTTLS failed for detection %s: %s", detection_hash or "unknown", exc)
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                client.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            client.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning("Email alert failed for detection %s: %s", detection_hash or "unknown", exc)
        return False

    _mark_sent("email", detection_hash)
    logger.info("Email alert sent for detection %s.", detection_hash or "unknown")
    return True
