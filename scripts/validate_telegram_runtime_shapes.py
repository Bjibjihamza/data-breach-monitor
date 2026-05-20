#!/usr/bin/env python3
"""Regression checks for Telegram stats shapes and Elasticsearch index idempotency."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.collectors.telegram_collector import TelegramCollectionStats
from app.storage.elastic_client import _resource_already_exists
from app.tasks import _telegram_progress_payload, _telegram_stat


def main() -> int:
    failures = 0

    stats = TelegramCollectionStats(
        channels_loaded=3,
        channels_processed=2,
        channels_with_errors=1,
        messages_seen=50,
        messages_collected=10,
    )
    if not hasattr(stats, "channels_processed"):
        print("[FAIL] TelegramCollectionStats missing channels_processed")
        failures += 1
    else:
        print("[PASS] TelegramCollectionStats.channels_processed exists")

    if stats.channels_scanned != stats.channels_processed:
        print("[FAIL] channels_scanned alias mismatch")
        failures += 1
    else:
        print("[PASS] channels_scanned alias matches channels_processed")

    payload = _telegram_progress_payload(stats, items_indexed=4)
    required = ("channels_total", "channels_processed", "messages_seen", "messages_collected")
    missing = [key for key in required if key not in payload]
    if missing:
        print(f"[FAIL] telegram progress payload missing keys: {missing}")
        failures += 1
    else:
        print("[PASS] telegram progress payload includes required keys")

    empty_stats = object()
    if int(_telegram_stat(empty_stats, "channels_processed", 0) or 0) != 0:
        print("[FAIL] _telegram_stat did not return default for missing attribute")
        failures += 1
    else:
        print("[PASS] _telegram_stat default for missing attribute")

    class FakeExc(Exception):
        def __init__(self) -> None:
            super().__init__("already exists")
            self.body = {"error": {"type": "resource_already_exists_exception"}}

    if not _resource_already_exists(FakeExc()):
        print("[FAIL] _resource_already_exists did not detect ES race error")
        failures += 1
    else:
        print("[PASS] _resource_already_exists detects resource_already_exists_exception")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
