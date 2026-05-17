from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from typing import Any
from urllib.parse import urlparse

from app.storage.elastic_client import INDEX_NAME, get_elastic_client, list_collection_runs
from app.storage.elastic_helpers import normalize_detection_document, search_total


SEVERITY_RANK = {"informational": 0, "low": 1, "medium": 2, "high": 3}
CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}
LEAK_KEYWORDS = {
    "breach",
    "leak",
    "leaked",
    "dump",
    "credentials",
    "password",
    "token",
    "secret",
    "database",
    "ransomware",
    "exploit",
    "zero-day",
}
STOP_WORDS = {
    "about",
    "after",
    "from",
    "have",
    "into",
    "more",
    "that",
    "this",
    "with",
    "your",
    "using",
    "message",
}


def _recent_detections(limit: int = 500) -> list[dict[str, Any]]:
    client = get_elastic_client()
    normalized_limit = min(max(1, limit), 1000)
    if not client.indices.exists(index=INDEX_NAME):
        return []
    response = client.search(
        index=INDEX_NAME,
        query={"match_all": {}},
        size=normalized_limit,
        sort=[{"processed_at": {"order": "desc", "unmapped_type": "date", "missing": "_last"}}],
    )
    hits = response.get("hits") if isinstance(response.get("hits"), dict) else {}
    hit_list = hits.get("hits") if isinstance(hits.get("hits"), list) else []
    return [normalize_detection_document(hit) for hit in hit_list if isinstance(hit, dict)]


def _highest(values: list[str], rank: dict[str, int], default: str) -> str:
    best = default
    best_rank = rank.get(best, 0)
    for value in values:
        candidate = str(value or "").lower()
        candidate_rank = rank.get(candidate, 0)
        if candidate_rank > best_rank:
            best = candidate
            best_rank = candidate_rank
    return best


def _host(value: str) -> str:
    if not value:
        return ""
    host = urlparse(value).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _tokens(value: str) -> list[str]:
    raw_tokens = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]{3,}", value.lower())
    return [token for token in raw_tokens if token not in STOP_WORDS]


def _similar_title_key(detection: dict[str, Any]) -> str:
    text = " ".join(
        [
            str(detection.get("title") or ""),
            str(detection.get("summary") or ""),
            str(detection.get("text") or ""),
        ]
    )
    useful = [token for token in _tokens(text) if token not in LEAK_KEYWORDS]
    if len(useful) < 3:
        return ""
    return " ".join(useful[:3])


def _correlation_id(correlation_type: str, key: str) -> str:
    digest = hashlib.sha1(f"{correlation_type}:{key}".encode("utf-8")).hexdigest()[:12]
    return f"{correlation_type}:{digest}"


def _add_group(groups: dict[tuple[str, str], list[dict[str, Any]]], kind: str, key: str, detection: dict[str, Any]) -> None:
    normalized = str(key or "").strip()
    if normalized and normalized.lower() not in {"unknown", "unmatched monitored feed", "telegram_public_channel"}:
        groups[(kind, normalized)].append(detection)


def get_correlations(limit: int = 500) -> dict[str, Any]:
    detections = _recent_detections(limit)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for detection in detections:
        _add_group(groups, "organization", str(detection.get("organization") or ""), detection)
        _add_group(groups, "source_domain", _host(str(detection.get("source_url") or detection.get("message_url") or "")), detection)
        for domain in detection.get("matched_domains") or []:
            _add_group(groups, "domain", str(domain), detection)
        for cve_id in detection.get("cve_ids") or []:
            _add_group(groups, "cve", str(cve_id).upper(), detection)
        for secret_type in detection.get("secret_types") or []:
            _add_group(groups, "secret_type", str(secret_type), detection)
        evidence_text = " ".join(
            [
                str(detection.get("title") or ""),
                str(detection.get("summary") or ""),
                str(detection.get("evidence_excerpt") or ""),
                str(detection.get("redacted_text") or ""),
            ]
        ).lower()
        for keyword in LEAK_KEYWORDS:
            if keyword in evidence_text:
                _add_group(groups, "leak_keyword", keyword, detection)
        title_key = _similar_title_key(detection)
        if title_key:
            _add_group(groups, "similar_title", title_key, detection)

    correlations: list[dict[str, Any]] = []
    for (kind, key), rows in groups.items():
        unique: dict[str, dict[str, Any]] = {}
        for row in rows:
            unique[str(row.get("detection_hash") or "")] = row
        detections_in_group = [row for hash_key, row in unique.items() if hash_key]
        if len(detections_in_group) < 2:
            continue
        sources = sorted({str(row.get("source") or "unknown") for row in detections_in_group})
        if kind in {"organization", "source_domain", "leak_keyword", "similar_title"} and len(sources) < 2:
            continue
        severity = _highest([str(row.get("severity") or "") for row in detections_in_group], SEVERITY_RANK, "informational")
        confidence = _highest([str(row.get("confidence") or "") for row in detections_in_group], CONFIDENCE_RANK, "low")
        correlations.append(
            {
                "correlation_id": _correlation_id(kind, key),
                "correlation_type": kind,
                "key": key,
                "involved_sources": sources,
                "detection_count": len(detections_in_group),
                "severity": severity,
                "confidence": confidence,
                "related_detection_hashes": [str(row.get("detection_hash")) for row in detections_in_group],
                "explanation": f"{len(detections_in_group)} related detections share {kind.replace('_', ' ')} '{key}' across {', '.join(sources)}.",
            }
        )

    correlations.sort(key=lambda item: (SEVERITY_RANK.get(str(item["severity"]), 0), item["detection_count"]), reverse=True)
    return {"total": len(correlations), "correlations": correlations[:100]}


def get_intelligence_summary(limit: int = 500) -> dict[str, Any]:
    detections = _recent_detections(limit)
    high_risk = [row for row in detections if str(row.get("severity") or "").lower() == "high"]
    affected_orgs = Counter(
        str(row.get("organization") or "unknown")
        for row in detections
        if str(row.get("organization") or "").lower() not in {"", "unknown", "unmatched monitored feed"}
    )
    risky_sources = Counter(str(row.get("source") or "unknown") for row in high_risk or detections)
    cves = Counter(cve for row in detections for cve in (row.get("cve_ids") or []))
    keywords = Counter(keyword for row in detections for keyword in (row.get("detected_keywords") or row.get("content_evidence") or []))
    confirmed = [
        row
        for row in detections
        if str(row.get("status") or "").lower() in {"confirmed", "escalated"}
        or (
            str(row.get("severity") or "").lower() == "high"
            and str(row.get("detection_category") or "").lower() in {"secret_exposure", "public_breach_news"}
        )
    ]

    actions: list[str] = []
    if high_risk:
        actions.append("Review high-severity detections first and confirm whether credentials or exposed systems are still active.")
    if cves:
        actions.append("Check repeated CVEs against the relevant asset inventory and patch status.")
    if affected_orgs:
        actions.append("Prioritize affected entities with repeated mentions across sources.")
    if any(row.get("secret_types") for row in detections):
        actions.append("Rotate exposed secrets and verify repository history cleanup for confirmed GitHub leaks.")
    if not actions:
        actions.append("Run an incremental collection and triage new detections before escalating.")

    return {
        "generated_from_detections": len(detections),
        "latest_high_risk_findings": high_risk[:10],
        "affected_organizations": [{"organization": key, "count": value} for key, value in affected_orgs.most_common(10)],
        "top_risk_sources": [{"source": key, "count": value} for key, value in risky_sources.most_common(10)],
        "repeated_cves": [{"cve_id": key, "count": value} for key, value in cves.most_common(10) if value >= 1],
        "repeated_keywords": [{"keyword": key, "count": value} for key, value in keywords.most_common(10) if value >= 1],
        "confirmed_exposure_signals": confirmed[:10],
        "recommended_actions": actions,
    }


def get_source_diagnostics(limit: int = 1) -> dict[str, Any]:
    sources = ("github", "google_alerts", "telegram")
    diagnostics: list[dict[str, Any]] = []
    for source in sources:
        runs = list_collection_runs(source=source, limit=limit).get("runs", [])
        latest = runs[0] if isinstance(runs, list) and runs else {}
        details = latest.get("details") if isinstance(latest.get("details"), dict) else {}
        if source == "github":
            rows = details.get("queries") if isinstance(details.get("queries"), list) else []
            row_type = "queries"
        elif source == "google_alerts":
            rows = details.get("feeds") if isinstance(details.get("feeds"), list) else []
            row_type = "feeds"
        else:
            rows = details.get("channels") if isinstance(details.get("channels"), list) else []
            row_type = "channels"
        diagnostics.append(
            {
                "source": source,
                "latest_run": latest,
                "row_type": row_type,
                "rows": rows,
            }
        )
    return {"sources": diagnostics}
