#!/usr/bin/env python3
"""Validate GitHub path classification and scoring behavior."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.collectors.github_scoring import apply_github_scoring_to_indicators
from app.detection.noise import classify_github_path
from app.processing.detector import detect_indicators


def _score_case(name: str, file_path: str, content: str) -> dict[str, object]:
    indicators = detect_indicators(
        content,
        file_path=file_path,
        content_only=True,
    )
    result = apply_github_scoring_to_indicators(content, file_path, indicators)
    return {
        "name": name,
        "path_classification": result.path_classification,
        "evidence_strength": result.evidence_strength,
        "severity": result.severity,
        "risk_score": result.risk_score,
        "should_index": result.should_index,
        "drop_reason": result.drop_reason,
        "scoring_reason": result.scoring_reason,
    }


def main() -> int:
    cases = [
        (
            "case1_env_example_placeholder",
            ".env.example",
            "DB_PASSWORD=your_password\n",
            lambda r: not r["should_index"]
            and r["drop_reason"] in {"placeholder_only", "template_weak"},
        ),
        (
            "case2_readme_changeme",
            "README.md",
            "password=changeme\n",
            lambda r: not r["should_index"],
        ),
        (
            "case3_env_template_empty_password",
            ".env.template",
            "DB_PASSWORD=\n",
            lambda r: not r["should_index"],
        ),
        (
            "case4_env_suspicious_path_only",
            ".env",
            "",
            lambda r: not r["should_index"] and r["drop_reason"] == "suspicious_path_only",
        ),
        (
            "case5_env_production_db_uri",
            ".env.production",
            "DATABASE_URL=postgres://user:realpass@host.example/db\n",
            lambda r: r["severity"] == "high" and r["should_index"],
        ),
        (
            "case6_env_example_real_aws_key",
            ".env.example",
            "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\nAWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n",
            lambda r: r["severity"] == "high" and r["should_index"],
        ),
    ]

    failures = 0
    for name, file_path, content, predicate in cases:
        path_class, _ = classify_github_path(file_path)
        result = _score_case(name, file_path, content)
        ok = predicate(result)
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(
            f"[{status}] {name}: path={path_class} strength={result['evidence_strength']} "
            f"severity={result['severity']} score={result['risk_score']} index={result['should_index']} "
            f"drop={result['drop_reason']}"
        )
        if not ok:
            print(f"       reason: {result['scoring_reason']}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
