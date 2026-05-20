from __future__ import annotations

from pydantic import BaseModel, Field


ALLOWED_DETECTION_STATUSES = frozenset(
    {"new", "reviewed", "ignored", "confirmed", "false_positive", "escalated"}
)


class DetectionStatusUpdate(BaseModel):
    status: str
    review_note: str | None = None
    reviewed_by: str | None = None


class DetectionListResponse(BaseModel):
    total: int
    limit: int
    offset: int = 0
    has_more: bool = False
    source: str | None = None
    items: list[dict[str, object]] = Field(default_factory=list)
    detections: list[dict[str, object]] = Field(default_factory=list)
