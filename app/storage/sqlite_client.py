from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import PROJECT_ROOT


DB_PATH = PROJECT_ROOT / "data" / "config.sqlite3"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def initialize_sqlite() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.commit()


# Future MVP tables:
# - watchlists: domains, keywords, owned assets, and authorized search scopes
# - source_configs: enabled collectors and rate-limit configuration
# - alert_rules: severity thresholds and destination routing
