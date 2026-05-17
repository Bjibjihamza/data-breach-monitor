from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import PROJECT_ROOT


DEFAULT_POLICY_PATH = PROJECT_ROOT / "config" / "detection_policy.yml"


@dataclass(frozen=True)
class DetectionPolicy:
    min_risk_score_to_index: int = 30
    ignore_placeholder_only: bool = True
    index_low_signals: bool = False
    example_paths_lower_confidence: bool = True
    placeholder_values: tuple[str, ...] = field(
        default_factory=lambda: (
            "",
            "null",
            "none",
            "changeme",
            "change_me",
            "your_key",
            "your-token",
            "example",
            "dummy",
            "test",
            "fake",
            "sample",
            "placeholder",
        )
    )
    example_path_patterns: tuple[str, ...] = field(
        default_factory=lambda: (
            ".env.example",
            ".env.sample",
            ".env.e2e.example",
            "README.md",
            "docs/",
            "examples/",
            "tests/",
            "fixtures/",
        )
    )


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _string_list(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    normalized: list[str] = []
    for value in values:
        if value is None:
            normalized.append("null")
        else:
            normalized.append(str(value))
    return tuple(normalized)


@lru_cache(maxsize=1)
def load_detection_policy(path: str | Path = DEFAULT_POLICY_PATH) -> DetectionPolicy:
    policy_path = Path(path)
    if not policy_path.exists():
        return DetectionPolicy()

    with policy_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        return DetectionPolicy()

    defaults = DetectionPolicy()
    placeholder_values = _string_list(payload.get("placeholder_values")) or defaults.placeholder_values
    example_path_patterns = (
        _string_list(payload.get("example_path_patterns")) or defaults.example_path_patterns
    )

    return DetectionPolicy(
        min_risk_score_to_index=_as_int(
            payload.get("min_risk_score_to_index"),
            defaults.min_risk_score_to_index,
        ),
        ignore_placeholder_only=_as_bool(
            payload.get("ignore_placeholder_only"),
            defaults.ignore_placeholder_only,
        ),
        index_low_signals=_as_bool(payload.get("index_low_signals"), defaults.index_low_signals),
        example_paths_lower_confidence=_as_bool(
            payload.get("example_paths_lower_confidence"),
            defaults.example_paths_lower_confidence,
        ),
        placeholder_values=placeholder_values,
        example_path_patterns=example_path_patterns,
    )

