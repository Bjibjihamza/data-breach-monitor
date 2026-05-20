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

    if lowered in {
        "password",
        "secret",
        "changeme",
        "change_me",
        "example",
        "example_password",
        "your_password",
        "your_api_key",
        "test",
        "demo",
        "local",
        "localhost",
        "127.0.0.1",
        "root:root",
        "admin:admin",
        "user:password",
        "dummy",
        "fake",
        "null",
        "none",
        "undefined",
        "false",
        "true",
        "0",
        "n/a",
        "admin",
        "root",
        "12345",
        "qwerty",
    }:
        return True, f"common placeholder value: {cleaned}"

    if lowered in {"password=password", "api_key=api_key", "secret=secret"}:
        return True, "self-referential placeholder assignment"

    if re.fullmatch(r"\$\{[A-Za-z0-9_.-]+\}", cleaned):
        return True, "environment variable template placeholder"
    if re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_]*", cleaned):
        return True, "shell-style variable placeholder"
    if re.fullmatch(r"%\([a-zA-Z0-9_]+\)s", cleaned):
        return True, "printf-style secret placeholder"
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


def _normalize_github_path(file_path: str) -> tuple[str, str]:
    normalized = (file_path or "").replace("\\", "/").strip().lower()
    basename = PurePosixPath(normalized).name if normalized else ""
    return normalized, basename


def classify_github_path(
    file_path: str,
    policy: DetectionPolicy | None = None,
) -> tuple[str, str]:
    """Classify a GitHub file path for scoring (strong_suspicious | weak_template | neutral)."""
    policy = policy or load_detection_policy()
    normalized, basename = _normalize_github_path(file_path)
    if not normalized:
        return "neutral", "no file path available"

    strong_names = frozenset(policy.github_strong_suspicious_basenames)
    if basename in strong_names:
        return "strong_suspicious", f"strong suspicious filename: {basename}"

    for strong_name in strong_names:
        if normalized.endswith(f"/{strong_name}") or normalized == strong_name:
            return "strong_suspicious", f"strong suspicious path: {strong_name}"

    is_example, example_reason = is_example_path(file_path, policy)
    if is_example:
        return "weak_template", example_reason

    template_names = frozenset(policy.github_template_basenames)
    if basename in template_names:
        return "weak_template", f"weak/template filename: {basename}"

    for weak_name in template_names:
        if normalized.endswith(f"/{weak_name}") or basename == weak_name:
            return "weak_template", f"weak/template path: {weak_name}"

    if any(marker in normalized for marker in policy.github_template_path_markers):
        return "weak_template", "path contains example/template/documentation marker"

    return "neutral", "standard path"


def is_github_weak_template_path(file_path: str, policy: DetectionPolicy | None = None) -> bool:
    classification, _ = classify_github_path(file_path, policy)
    return classification == "weak_template"

