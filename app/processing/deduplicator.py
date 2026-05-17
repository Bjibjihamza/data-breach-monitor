from __future__ import annotations

import hashlib


def detection_hash(detection: dict[str, object]) -> str:
    hash_input = "|".join(
        [
            str(detection.get("source", "")),
            str(detection.get("source_url", "")),
            str(detection.get("redacted_text", "")),
        ]
    )
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def add_detection_hash(detection: dict[str, object]) -> dict[str, object]:
    detection["detection_hash"] = detection_hash(detection)
    return detection
