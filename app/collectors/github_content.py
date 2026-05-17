from __future__ import annotations

import logging
from typing import Any

import requests

from app.config import settings


logger = logging.getLogger(__name__)


def fetch_repository_file_content(
    item: dict[str, Any],
    headers: dict[str, str],
) -> tuple[str | None, str | None]:
    """
    Fetch raw file content for a GitHub code search result item.
    Returns (content, error_reason).
    """
    file_url = item.get("url")
    if not file_url:
        return None, "missing_file_url"

    fetch_headers = {
        **headers,
        "Accept": "application/vnd.github.raw",
    }
    timeout = max(1, settings.GITHUB_CONTENT_FETCH_TIMEOUT)
    max_bytes = max(1024, settings.GITHUB_MAX_CONTENT_BYTES)

    try:
        response = requests.get(file_url, headers=fetch_headers, timeout=timeout)
    except requests.Timeout:
        logger.warning("Timeout fetching GitHub file content: %s", file_url)
        return None, "timeout"
    except requests.RequestException as exc:
        logger.warning(
            "Failed to fetch GitHub file content from %s: %s",
            file_url,
            exc.__class__.__name__,
        )
        return None, "request_error"

    if response.status_code == 404:
        return None, "not_found"
    if response.status_code >= 400:
        return None, f"http_{response.status_code}"

    encoding = (response.headers.get("Content-Encoding") or "").lower()
    if encoding and encoding not in {"identity", "none"}:
        logger.warning("Skipping GitHub file with unsupported encoding %s", encoding)
        return None, "unsupported_encoding"

    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                logger.info(
                    "Truncating GitHub file content from %s bytes to %s bytes",
                    content_length,
                    max_bytes,
                )
        except ValueError:
            pass

    content = response.content[:max_bytes].decode("utf-8", errors="replace")
    if not content.strip():
        return None, "empty_content"
    return content, None
