from __future__ import annotations

from pydantic import BaseModel


class AlertPayload(BaseModel):
    detection_hash: str
    source: str
    source_url: str
    severity: str
    risk_score: int
    message: str
