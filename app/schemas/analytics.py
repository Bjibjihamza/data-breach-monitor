from __future__ import annotations

from pydantic import BaseModel, Field


ALLOWED_TIMELINE_INTERVALS = frozenset({"hour", "day"})
DEFAULT_TIMELINE_DAYS = 7
MAX_TIMELINE_DAYS = 90


class AnalyticsSummaryResponse(BaseModel):
    total_detections: int
    detections_by_source: dict[str, int] = Field(default_factory=dict)
    detections_by_signal_type: dict[str, int] = Field(default_factory=dict)
    detections_by_organization: dict[str, int] = Field(default_factory=dict)
    detections_by_category: dict[str, int] = Field(default_factory=dict)
    detections_by_country: dict[str, int] = Field(default_factory=dict)
    detections_by_risk_category: dict[str, int] = Field(default_factory=dict)
    detections_by_confidence: dict[str, int] = Field(default_factory=dict)
    detections_by_severity: dict[str, int] = Field(default_factory=dict)
    detections_by_status: dict[str, int] = Field(default_factory=dict)
    latest_detections: list[dict[str, object]] = Field(default_factory=list)


class TimelinePoint(BaseModel):
    timestamp: str
    count: int


class AnalyticsTimelineResponse(BaseModel):
    interval: str
    days: int
    points: list[TimelinePoint] = Field(default_factory=list)
