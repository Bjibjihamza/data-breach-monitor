from __future__ import annotations

import re

from app.processing.detector import (
    API_KEY_ASSIGNMENT_RE,
    AWS_ACCESS_KEY_RE,
    BEARER_TOKEN_RE,
    DB_URI_RE,
    GITHUB_TOKEN_RE,
    JWT_RE,
    LOOSE_EXPOSURE_PATTERNS,
    OPENAI_KEY_RE,
    PASSWORD_ASSIGNMENT_RE,
    PRIVATE_KEY_RE,
    TOKEN_ASSIGNMENT_RE,
)
from app.processing.redactor import redact_evidence_line

MAX_EVIDENCE_EXCERPT_CHARS = 2000


def line_has_content_evidence(line: str) -> bool:
    """True when a single content line contains exposure evidence (not query metadata)."""
    if not line.strip():
        return False
    if PRIVATE_KEY_RE.search(line):
        return True
    if any(pattern.search(line) for pattern in LOOSE_EXPOSURE_PATTERNS):
        return True
    if DB_URI_RE.search(line):
        return True
    if PASSWORD_ASSIGNMENT_RE.search(line):
        return True
    if API_KEY_ASSIGNMENT_RE.search(line):
        return True
    if TOKEN_ASSIGNMENT_RE.search(line):
        return True
    if GITHUB_TOKEN_RE.search(line):
        return True
    if OPENAI_KEY_RE.search(line):
        return True
    if AWS_ACCESS_KEY_RE.search(line):
        return True
    if JWT_RE.search(line):
        return True
    if BEARER_TOKEN_RE.search(line):
        return True
    if re.search(r"\bdb_password\b", line, re.IGNORECASE) and re.search(r"[:=]", line):
        return True
    if re.search(r"\b(?:api_key|secret_key|jwt_secret)\b", line, re.IGNORECASE) and re.search(
        r"[:=]", line
    ):
        return True
    return False


def extract_line_evidence(content: str) -> dict[str, list[str] | list[int] | str]:
    """Extract redacted evidence lines from file content only."""
    evidence_lines: list[str] = []
    evidence_line_numbers: list[int] = []
    excerpt_parts: list[str] = []

    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        if not line_has_content_evidence(raw_line):
            continue
        redacted_line = redact_evidence_line(raw_line.rstrip())
        evidence_line_numbers.append(line_number)
        evidence_lines.append(f"{line_number}: {redacted_line}")
        excerpt_parts.append(redacted_line)

    excerpt = "\n".join(excerpt_parts)
    if len(excerpt) > MAX_EVIDENCE_EXCERPT_CHARS:
        excerpt = excerpt[: MAX_EVIDENCE_EXCERPT_CHARS - 3] + "..."

    return {
        "evidence_lines": evidence_lines,
        "evidence_line_numbers": evidence_line_numbers,
        "evidence_excerpt": excerpt,
    }
