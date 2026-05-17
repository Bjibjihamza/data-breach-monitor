from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.detections import router as detections_router
from app.detection.extractors import ExtractedSecret
from app.detection.scoring import score_validated_detection
from app.detection.validators import validate_candidate
from app.processing.deduplicator import detection_hash
from app.storage.elastic_client import _source_health_from_run
from app.watchlists import loader


class DetectionScoringTests(unittest.TestCase):
    def test_high_value_secret_scores_high(self) -> None:
        candidate = ExtractedSecret(
            key="GITHUB_TOKEN",
            value="ghp_" + "A" * 36,
            line_number=1,
            context="GITHUB_TOKEN=...",
            raw="GITHUB_TOKEN=...",
        )
        validation = validate_candidate(candidate)
        decision = score_validated_detection(
            file_path=".env",
            is_example_path=False,
            extracted_count=1,
            placeholder_count=0,
            validations=[validation],
            has_sensitive_keywords=True,
            has_suspicious_path=True,
            has_domains=False,
            has_watchlist=True,
        )
        self.assertEqual(decision.final_decision, "index")
        self.assertEqual(decision.severity, "high")

    def test_placeholder_only_signal_is_ignored(self) -> None:
        decision = score_validated_detection(
            file_path=".env.example",
            is_example_path=True,
            extracted_count=1,
            placeholder_count=1,
            validations=[],
            has_sensitive_keywords=True,
            has_suspicious_path=True,
            has_domains=False,
            has_watchlist=False,
        )
        self.assertEqual(decision.final_decision, "ignore")
        self.assertTrue(decision.is_noise)


class DeduplicationTests(unittest.TestCase):
    def test_detection_hash_is_stable(self) -> None:
        detection = {
            "source": "github",
            "source_url": "https://github.com/acme/repo/blob/main/.env",
            "redacted_text": "TOKEN=[REDACTED]",
        }
        self.assertEqual(detection_hash(detection), detection_hash(dict(detection)))


class WatchlistLoadingTests(unittest.TestCase):
    def test_organization_watchlists_are_disabled_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            watchlist = root / "organizations_watchlist.yml"
            watchlist.write_text(
                """
organizations:
  - name: Acme
    domains:
      - acme.example
""",
                encoding="utf-8",
            )
            with patch.object(
                loader,
                "settings",
                SimpleNamespace(
                    WATCHLISTS_ORGANIZATIONS_DIR=root / "missing",
                    WATCHLISTS_ORGANIZATIONS_FILE=watchlist,
                    ORGANIZATION_WATCHLISTS_ENABLED=False,
                    WATCHLISTS_GLOBAL_RISKS_PATH=root / "missing.yml",
                    GITHUB_SEARCH_QUERIES=[],
                ),
            ):
                loader._cached_organizations = None
                self.assertEqual(loader.load_organizations(refresh=True), [])

    def test_loads_config_organizations_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            watchlist = root / "organizations_watchlist.yml"
            watchlist.write_text(
                """
organizations:
  - name: Acme
    category: fintech
    country: MA
    domains:
      - acme.example
    keywords:
      - Acme Payments
    email_patterns:
      - "@acme.example"
    github_queries:
      - '"acme.example" "API_KEY"'
    source_settings:
      github:
        enabled: true
""",
                encoding="utf-8",
            )
            with patch.object(
                loader,
                "settings",
                SimpleNamespace(
                    WATCHLISTS_ORGANIZATIONS_DIR=root / "missing",
                    WATCHLISTS_ORGANIZATIONS_FILE=watchlist,
                    ORGANIZATION_WATCHLISTS_ENABLED=True,
                    WATCHLISTS_GLOBAL_RISKS_PATH=root / "missing.yml",
                    GITHUB_SEARCH_QUERIES=[],
                ),
            ):
                loader._cached_organizations = None
                profiles = loader.load_organizations(refresh=True)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0].name, "Acme")
        self.assertIn("acme.example", profiles[0].watch_terms())
        self.assertEqual(profiles[0].source_settings["github"]["enabled"], True)

    def test_github_specs_are_global_first_when_orgs_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            risks = root / "global_risks.yml"
            risks.write_text(
                """
categories:
  env_files:
    name: Environment files
    severity_hint: high
    queries:
      - query: 'filename:.env DB_PASSWORD'
""",
                encoding="utf-8",
            )
            org_file = root / "organizations_watchlist.yml"
            org_file.write_text(
                """
organizations:
  - name: Acme
    github_queries:
      - '"acme.example" "API_KEY"'
""",
                encoding="utf-8",
            )
            with patch.object(
                loader,
                "settings",
                SimpleNamespace(
                    WATCHLISTS_ORGANIZATIONS_DIR=root / "missing",
                    WATCHLISTS_ORGANIZATIONS_FILE=org_file,
                    ORGANIZATION_WATCHLISTS_ENABLED=False,
                    WATCHLISTS_GLOBAL_RISKS_PATH=risks,
                    GITHUB_SEARCH_QUERIES=[],
                ),
            ):
                loader._cached_organizations = None
                loader._cached_global_risks = None
                specs = loader.github_search_specs()
        self.assertEqual([spec.query for spec in specs], ["filename:.env DB_PASSWORD"])
        self.assertEqual(specs[0].organization, "")


class StatusEndpointTests(unittest.TestCase):
    def test_status_update_endpoint_returns_success(self) -> None:
        app = FastAPI()
        app.include_router(detections_router)
        client = TestClient(app)
        with patch(
            "app.api.detections.update_detection_status",
            return_value={"detection_hash": "abc", "status": "reviewed"},
        ):
            response = client.patch(
                "/detections/abc/status",
                json={"status": "reviewed", "review_note": "checked", "reviewed_by": "tester"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "reviewed")


class AlertMissingEnvTests(unittest.TestCase):
    def test_telegram_alert_missing_env_returns_false(self) -> None:
        from app.alerts import telegram_alert

        with patch.object(telegram_alert, "settings", SimpleNamespace(TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="")):
            self.assertFalse(telegram_alert.send_telegram_alert({"detection_hash": "abc"}))

    def test_email_alert_missing_env_returns_false(self) -> None:
        from app.alerts import email_alert

        settings = SimpleNamespace(
            SMTP_HOST="",
            SMTP_PORT="",
            SMTP_USER="",
            SMTP_PASSWORD="",
            ALERT_EMAIL_TO="",
        )
        with patch.object(email_alert, "settings", settings):
            self.assertFalse(email_alert.send_email_alert({"detection_hash": "abc"}))


class SourceHealthTests(unittest.TestCase):
    def test_github_success_with_zero_indexed_is_healthy(self) -> None:
        run = {
            "_source": {
                "source": "github",
                "status": "success",
                "collected": 0,
                "indexed": 0,
                "duplicates_skipped": 0,
                "errors": 0,
                "started_at": "2026-05-17T10:00:00Z",
                "ended_at": "2026-05-17T10:01:00Z",
                "message": "GitHub scan completed successfully",
                "details": {},
            }
        }

        health = _source_health_from_run("github", "GitHub", True, run)

        self.assertEqual(health["status"], "healthy")
        self.assertEqual(health["scan_result"], "completed")
        self.assertEqual(health["indexed_count"], 0)
        self.assertEqual(health["warning_count"], 0)
        self.assertIn("No new validated detections", health["message"])

    def test_github_rate_limit_is_warning(self) -> None:
        run = {
            "_source": {
                "source": "github",
                "status": "success",
                "indexed": 0,
                "duplicates_skipped": 0,
                "errors": 0,
                "message": "GitHub scan completed with recoverable issues",
                "details": {"rate_limited": True},
            }
        }

        health = _source_health_from_run("github", "GitHub", True, run)

        self.assertEqual(health["status"], "warning")
        self.assertEqual(health["scan_result"], "partial")
        self.assertGreaterEqual(health["warning_count"], 1)
        self.assertIn("rate limit reached", health["message"])


if __name__ == "__main__":
    unittest.main()
