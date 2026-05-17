from __future__ import annotations

from datetime import datetime, timezone

from app.config import settings


def collect_mock_paste_events() -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    if not settings.MOCK_PASTE_DIR.exists():
        print(f"Mock paste directory not found: {settings.MOCK_PASTE_DIR}")
        return events

    for path in sorted(settings.MOCK_PASTE_DIR.glob("*.txt")):
        raw_text = path.read_text(encoding="utf-8")
        events.append(
            {
                "source": "mock_paste",
                "source_url": str(path.name),
                "title": path.stem,
                "raw_text": raw_text,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    return events
