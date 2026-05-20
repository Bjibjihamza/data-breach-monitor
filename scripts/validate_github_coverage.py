#!/usr/bin/env python3
"""Validate GitHub extraction, validation, scoring, and redaction for Phase 3 coverage."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.collectors.github_scoring import apply_github_scoring_to_indicators
from app.detection.extractors import extract_secret_candidates
from app.detection.validators import validate_candidate
from app.processing.detector import detect_indicators
from app.processing.redactor import redact_sensitive_values


def _pipeline(file_path: str, content: str) -> dict[str, object]:
    indicators = detect_indicators(content, file_path=file_path, content_only=True)
    score = apply_github_scoring_to_indicators(content, file_path, indicators)
    redacted = redact_sensitive_values(content)
    candidates = extract_secret_candidates(content)
    validations = [
        validate_candidate(candidate)
        for candidate in candidates
        if candidate.key or candidate.value
    ]
    validated = [item for item in validations if item.get("is_valid_candidate")]
    return {
        "indicators": indicators,
        "score": score,
        "redacted": redacted,
        "validated_count": len(validated),
        "secret_types": list(indicators.get("secret_types") or []),
        "should_index": score.should_index,
        "severity": score.severity,
        "drop_reason": score.drop_reason,
    }


def main() -> int:
    cases = [
        (
            "case1_vercel_token",
            ".env",
            "VERCEL_TOKEN=vcel_abcdefghijklmnopqrstuvwxyz123456\n",
            lambda r: r["validated_count"] >= 1
            and r["should_index"]
            and r["severity"] in {"medium", "high"},
        ),
        (
            "case2_supabase_service_role_jwt",
            ".env",
            "SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSJ9.c2lnbmF0dXJlMTIzNDU2Nzg5MA\n",
            lambda r: "supabase_service_role_key" in r["secret_types"]
            and r["should_index"]
            and r["severity"] == "high",
        ),
        (
            "case3_cloudflare_api_token",
            ".env",
            "CLOUDFLARE_API_TOKEN=abcdefghijklmnopqrstuvwxyz1234567890ABCD\n",
            lambda r: "cloudflare_api_token" in r["secret_types"]
            and r["should_index"]
            and r["severity"] in {"medium", "high"},
        ),
        (
            "case4_notion_readme_placeholder",
            "README.md",
            "NOTION_TOKEN=your_token\n",
            lambda r: not r["should_index"],
        ),
        (
            "case5_k8s_stringdata_changeme",
            "secret.yaml",
            "apiVersion: v1\nkind: Secret\nstringData:\n  password: changeme\n",
            lambda r: not r["should_index"],
        ),
        (
            "case6_k8s_stringdata_realistic",
            "secret.yaml",
            "apiVersion: v1\nkind: Secret\nstringData:\n  apiKey: xK9mP2nQ7vR4sT8uW1yZ3aB6cD0eF5gH\n",
            lambda r: r["validated_count"] >= 1
            and r["should_index"]
            and r["severity"] in {"medium", "high"},
        ),
        (
            "case7_dockerfile_changeme",
            "Dockerfile",
            "ENV DB_PASSWORD=changeme\n",
            lambda r: not r["should_index"],
        ),
        (
            "case8_dockerfile_postgres_uri",
            "Dockerfile",
            "ENV DATABASE_URL=postgres://user:realpass@db.example.com/app\n",
            lambda r: r["should_index"] and r["severity"] == "high",
        ),
        (
            "case9_google_services_json",
            "google-services.json",
            '{"client":[{"api_key":[{"current_key":"AIzaSyD4f9GhJkLmN0pQrStUvWxYz1234567890"}]}]}\n',
            lambda r: "google_api_key" in r["secret_types"]
            and "AIzaSy" not in r["redacted"],
        ),
        (
            "case10_gitlab_token",
            ".env",
            "GITLAB_TOKEN=glpat-abcdefghijklmnopqrst\n",
            lambda r: "gitlab_token" in r["secret_types"]
            and "glpat-" not in r["redacted"],
        ),
    ]

    failures = 0
    for name, file_path, content, predicate in cases:
        result = _pipeline(file_path, content)
        ok = predicate(result)
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(
            f"[{status}] {name}: types={result['secret_types']} severity={result['severity']} "
            f"index={result['should_index']} drop={result['drop_reason']} validated={result['validated_count']}"
        )
        if not ok:
            print(f"       redacted sample: {result['redacted'][:120]!r}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
