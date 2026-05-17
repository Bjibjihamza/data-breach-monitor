from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
logger = logging.getLogger(__name__)


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        logger.warning("Invalid integer for %s=%r; using default %s.", name, raw_value, default)
        return default
    if parsed < minimum:
        logger.warning("Invalid value for %s=%r; using minimum %s.", name, raw_value, minimum)
        return minimum
    return parsed


def _interval_minutes(value: str | None, default: int, *, minimum: int = 5) -> int:
    parsed = _int(value or "", default)
    return max(minimum, parsed)


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on", "enabled"}


_VALID_SCAN_MODES = {"backfill", "incremental"}


def _env_scan_mode(name: str, default: str) -> str:
    raw_value = (os.getenv(name) or "").strip().lower()
    if raw_value in _VALID_SCAN_MODES:
        return raw_value
    if raw_value:
        logger.warning("Invalid scan mode for %s=%r; using default %s.", name, raw_value, default)
    return default


@dataclass(frozen=True)
class Settings:
    APP_ENV: str = os.getenv("APP_ENV", "development")
    ELASTICSEARCH_URL: str = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    GOOGLE_ALERTS_RSS_URL: str = os.getenv("GOOGLE_ALERTS_RSS_URL", "")
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    GITHUB_SEARCH_QUERIES: list[str] = field(default_factory=lambda: _csv(os.getenv("GITHUB_SEARCH_QUERIES", "")))
    GITHUB_MAX_RESULTS_PER_QUERY: int = _env_int("GITHUB_MAX_RESULTS_PER_QUERY", 30)
    GITHUB_MAX_QUERIES_PER_RUN: int = _env_int("GITHUB_MAX_QUERIES_PER_RUN", 20)
    GITHUB_MAX_FILE_FETCHES_PER_RUN: int = _env_int("GITHUB_MAX_FILE_FETCHES_PER_RUN", 50)
    GITHUB_MAX_PAGES_PER_QUERY: int = _env_int("GITHUB_MAX_PAGES_PER_QUERY", 2)
    GITHUB_MAX_CONTENT_BYTES: int = _int(os.getenv("GITHUB_MAX_CONTENT_BYTES", str(512 * 1024)), 512 * 1024)
    GITHUB_CONTENT_FETCH_TIMEOUT: int = _int(os.getenv("GITHUB_CONTENT_FETCH_TIMEOUT", "15"), 15)
    GOOGLE_ALERTS_MAX_ENTRIES_PER_FEED: int = _env_int("GOOGLE_ALERTS_MAX_ENTRIES_PER_FEED", 25)
    GOOGLE_ALERTS_MAX_FEEDS_PER_RUN: int = _env_int("GOOGLE_ALERTS_MAX_FEEDS_PER_RUN", 20)
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    TELEGRAM_API_ID: int = _int(os.getenv("TELEGRAM_API_ID", "0"), 0)
    TELEGRAM_API_HASH: str = os.getenv("TELEGRAM_API_HASH", "")
    TELEGRAM_SESSION_NAME: str = os.getenv("TELEGRAM_SESSION_NAME", "data_breach_monitor")
    TELEGRAM_LIMIT_PER_CHANNEL: int = _env_int("TELEGRAM_LIMIT_PER_CHANNEL", 20)
    COLLECTION_INTERVAL_MINUTES: int = _interval_minutes(os.getenv("COLLECTION_INTERVAL_MINUTES"), 30)
    GOOGLE_ALERTS_INTERVAL_MINUTES: int = _interval_minutes(
        os.getenv("GOOGLE_ALERTS_INTERVAL_MINUTES"),
        COLLECTION_INTERVAL_MINUTES,
    )
    TELEGRAM_INTERVAL_MINUTES: int = _interval_minutes(
        os.getenv("TELEGRAM_INTERVAL_MINUTES"),
        COLLECTION_INTERVAL_MINUTES,
    )
    GITHUB_INTERVAL_MINUTES: int = _interval_minutes(os.getenv("GITHUB_INTERVAL_MINUTES"), 60)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: str = os.getenv("SMTP_PORT", "")
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    ALERT_EMAIL_TO: str = os.getenv("ALERT_EMAIL_TO", "")
    MOCK_PASTE_DIR: Path = PROJECT_ROOT / "data" / "mock_pastes"
    WATCHLISTS_ORGANIZATIONS_DIR: Path = Path(
        os.getenv(
            "WATCHLISTS_ORGANIZATIONS_DIR",
            str(PROJECT_ROOT / "app" / "watchlists" / "organizations"),
        )
    )
    WATCHLISTS_ORGANIZATIONS_FILE: Path = Path(
        os.getenv(
            "WATCHLISTS_ORGANIZATIONS_FILE",
            str(PROJECT_ROOT / "config" / "organizations_watchlist.yml"),
        )
    )
    ORGANIZATION_WATCHLISTS_ENABLED: bool = _env_bool("ORGANIZATION_WATCHLISTS_ENABLED", False)
    WATCHLISTS_GLOBAL_RISKS_PATH: Path = Path(
        os.getenv(
            "WATCHLISTS_GLOBAL_RISKS_PATH",
            str(PROJECT_ROOT / "app" / "watchlists" / "global_risks.yml"),
        )
    )
    INITIAL_BACKFILL_ENABLED: bool = _env_bool("INITIAL_BACKFILL_ENABLED", True)
    INITIAL_BACKFILL_RUN_ON_STARTUP: bool = _env_bool("INITIAL_BACKFILL_RUN_ON_STARTUP", True)
    INITIAL_BACKFILL_MAX_ITEMS_PER_SOURCE: int = _env_int(
        "INITIAL_BACKFILL_MAX_ITEMS_PER_SOURCE", 500
    )
    GITHUB_INCREMENTAL_MAX_ITEMS: int = _env_int("GITHUB_INCREMENTAL_MAX_ITEMS", 50)
    GOOGLE_ALERTS_INCREMENTAL_MAX_ITEMS: int = _env_int("GOOGLE_ALERTS_INCREMENTAL_MAX_ITEMS", 50)
    TELEGRAM_INCREMENTAL_MAX_ITEMS: int = _env_int("TELEGRAM_INCREMENTAL_MAX_ITEMS", 50)
    GITHUB_DEFAULT_SCAN_MODE: str = _env_scan_mode("GITHUB_SCAN_MODE", "incremental")


settings = Settings()
