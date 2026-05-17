from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RawEvent(BaseModel):
    source: str
    title: str
    raw_text: str
    url: str | None = None
    source_url: str | None = None
    timestamp: str | None = None
    collected_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
