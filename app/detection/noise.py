from __future__ import annotations

import re
from pathlib import PurePosixPath

from app.detection.policy import DetectionPolicy, load_detection_policy


_SENSITIVE_PLACEHOLDER_WORDS = {
    "key",
    "token",
    "secret",
    "password",
    "passwd",
    "pwd",
    "client",
    "auth",
    "api",
}

_PLACEHOLDER_TOKENS = {
    "changeme",
    "change",
    "me",
    "your",
    "example",
    "dummy",
    "fake",
    "sample",
    "placeholder",
    "insert",
    "replace",
    "todo",
    "test",
    "xxx",
}


def normalize_secret_value(value: object) -> str:
    if value is None:
        return ""
    cleaned = str(value).strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _tokenize(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", value.lower()) if token}


def is_placeholder_value(
    value: object,
    policy: DetectionPolicy | None = None,
) -> tuple[bool, str]:
    policy = policy or load_detection_policy()
    cleaned = normalize_secret_value(value)
    lowered = cleaned.lower()

    if value is None:
        return True, "null placeholder value"
    if cleaned == "":
        return True, "empty placeholder value"

    configured = {normalize_secret_value(item).lower() for item in policy.placeholder_values}
    if lowered in configured:
        return True, f"configured placeholder value: {cleaned}"

    if re.fullmatch(r"\$\{[A-Za-z0-9_.-]+\}", cleaned):
        return True, "environment variable template placeholder"
    if re.fullmatch(r"<[^>]+>", cleaned):
        tokens = _tokenize(cleaned)
        if tokens & _SENSITIVE_PLACEHOLDER_WORDS:
            return True, "angle-bracket secret placeholder"
    if re.fullmatch(r"(?:x+|\*+|_+|-+)", lowered):
        return True, "masked placeholder value"
    if re.fullmatch(r"(?:your|insert|replace|change)[-_ ]?[a-z0-9_-]*(?:here)?", lowered):
        return True, "instructional placeholder value"
    if lowered.endswith("_here") and {"key", "token", "secret", "password"} & _tokenize(lowered):
        return True, "instructional placeholder value"

    tokens = _tokenize(lowered)
    if tokens and tokens <= (_PLACEHOLDER_TOKENS | _SENSITIVE_PLACEHOLDER_WORDS):
        return True, "placeholder words only"

    return False, ""


def is_example_path(path: str, policy: DetectionPolicy | None = None) -> tuple[bool, str]:
    policy = policy or load_detection_policy()
    if not path:
        return False, ""

    normalized = path.replace("\\", "/").lower()
    basename = PurePosixPath(normalized).name
    for raw_pattern in policy.example_path_patterns:
        pattern = raw_pattern.replace("\\", "/").lower()
        if not pattern:
            continue
        if pattern.endswith("/"):
            marker = f"/{pattern.strip('/')}/"
            if normalized.startswith(pattern) or marker in f"/{normalized}/":
                return True, f"example/documentation path pattern: {raw_pattern}"
            continue
        if normalized.endswith(pattern) or basename == pattern:
            return True, f"example/documentation path pattern: {raw_pattern}"

    return False, ""

