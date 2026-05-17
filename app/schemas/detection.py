from __future__ import annotations

from pydantic import BaseModel, Field


class Detection(BaseModel):
    source: str
    source_url: str
    title: str
    organization: str = ""
    risk_category: str = ""
    confidence: str = ""
    collected_at: str
    processed_at: str
    matched_emails: list[str] = Field(default_factory=list)
    matched_domains: list[str] = Field(default_factory=list)
    matched_watchlist: list[str] = Field(default_factory=list)
    detected_indicators: list[str] = Field(default_factory=list)
    evidence_lines: list[str] = Field(default_factory=list)
    evidence_line_numbers: list[int] = Field(default_factory=list)
    evidence_excerpt: str = ""
    redacted_text: str
    risk_score: int
    severity: str
    is_noise: bool = False
    noise_reason: str = ""
    extracted_secrets_count: int = 0
    validated_secrets_count: int = 0
    placeholder_count: int = 0
    secret_types: list[str] = Field(default_factory=list)
    validation_reasons: list[str] = Field(default_factory=list)
    final_decision: str = "index"
    triage_status: str = "new"
    confidence_score: int = 0
    status: str = "new"
    detection_hash: str | None = None
