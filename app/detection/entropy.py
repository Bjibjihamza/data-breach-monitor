from __future__ import annotations

import math
import re
from collections import Counter


MIN_SECRET_LENGTH = 8


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def looks_random(value: str) -> bool:
    cleaned = value.strip()
    if len(cleaned) < MIN_SECRET_LENGTH:
        return False
    if re.fullmatch(r"[A-Za-z]+(?:[-_\s][A-Za-z]+)*", cleaned):
        return False
    entropy = shannon_entropy(cleaned)
    if len(cleaned) >= 32 and entropy >= 3.4:
        return True
    if len(cleaned) >= 20 and entropy >= 3.7:
        return True
    return len(cleaned) >= 12 and entropy >= 4.0


def entropy_confidence(value: str) -> tuple[str, int, str]:
    cleaned = value.strip()
    if not cleaned:
        return "low", 0, "empty value"
    if len(cleaned) < MIN_SECRET_LENGTH:
        return "low", 10, "value shorter than 8 characters"

    entropy = shannon_entropy(cleaned)
    if looks_random(cleaned):
        if len(cleaned) >= 32 and entropy >= 4.0:
            return "high", 85, f"high entropy value ({entropy:.2f})"
        return "medium", 60, f"random-looking value ({entropy:.2f})"

    return "low", 25, f"low entropy or human-readable value ({entropy:.2f})"

