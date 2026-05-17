from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)

UNKNOWN_LABEL = "unknown"
SUMMARY_AGG_FIELDS: dict[str, tuple[str, int]] = {
    "by_source": ("source", 100),
    "by_signal_type": ("signal_type", 50),
    "by_organization": ("organization", 100),
    "by_category": ("category", 50),
    "by_country": ("country", 50),
    "by_risk_category": ("risk_category", 50),
    "by_confidence": ("confidence", 10),
    "by_severity": ("severity", 20),
    "by_status": ("status", 20),
    "by_final_decision": ("final_decision", 10),
    "by_triage_status": ("triage_status", 20),
    "by_secret_type": ("secret_types", 50),
}


def index_properties(mapping_response: dict[str, Any]) -> dict[str, Any]:
    if not mapping_response:
        return {}
    first_index = next(iter(mapping_response.values()), {})
    properties = first_index.get("mappings", {}).get("properties", {})
    return properties if isinstance(properties, dict) else {}


def build_terms_aggregations(properties: dict[str, Any]) -> dict[str, Any]:
    aggregations: dict[str, Any] = {}
    for agg_name, (field_name, size) in SUMMARY_AGG_FIELDS.items():
        if field_name not in properties:
            logger.debug("Skipping aggregation %s; field %s is not mapped.", agg_name, field_name)
            continue
        aggregations[agg_name] = {
            "terms": {
                "field": field_name,
                "size": size,
                "missing": UNKNOWN_LABEL,
            }
        }
    return aggregations


def resolve_timeline_date_field(properties: dict[str, Any]) -> str | None:
    if "processed_at" in properties:
        return "processed_at"
    if "collected_at" in properties:
        return "collected_at"
    if "published_at" in properties:
        return "published_at"
    return None


def terms_aggregation_dict(aggregation: dict[str, Any] | None) -> dict[str, int]:
    if not isinstance(aggregation, dict):
        return {}

    buckets = aggregation.get("buckets")
    if not isinstance(buckets, list):
        return {}

    counts: dict[str, int] = {}
    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        raw_key = bucket.get("key")
        if raw_key is None or raw_key == "":
            label = UNKNOWN_LABEL
        else:
            label = str(raw_key)
        counts[label] = int(bucket.get("doc_count", 0))
    return counts


def search_total(hits_payload: dict[str, Any] | None) -> int:
    if not isinstance(hits_payload, dict):
        return 0
    total = hits_payload.get("total", 0)
    if isinstance(total, dict):
        return int(total.get("value", 0))
    try:
        return int(total)
    except (TypeError, ValueError):
        return 0


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def normalize_detection_document(hit: dict[str, Any]) -> dict[str, Any]:
    """Normalize old and new Elasticsearch documents for API responses."""
    source = hit.get("_source", hit)
    if not isinstance(source, dict):
        source = {}

    document = dict(source)
    document["detection_hash"] = str(document.get("detection_hash") or hit.get("_id") or UNKNOWN_LABEL)
    document["source"] = str(document.get("source") or UNKNOWN_LABEL)
    document["signal_type"] = str(document.get("signal_type") or "")
    document["source_url"] = str(document.get("source_url") or document.get("url") or "")
    document["source_name"] = str(document.get("source_name") or "")
    document["title"] = str(document.get("title") or "")
    document["summary"] = str(document.get("summary") or "")
    document["text"] = str(document.get("text") or "")
    document["alert_name"] = str(document.get("alert_name") or "")
    document["category"] = str(document.get("category") or document.get("detection_category") or "")
    document["country"] = str(document.get("country") or "")
    document["query"] = str(document.get("query") or document.get("search_query_context") or "")
    document["published_at"] = str(document.get("published_at") or "")
    document["matched_organization"] = str(document.get("matched_organization") or "")
    document["matched_organizations"] = _as_str_list(document.get("matched_organizations"))
    document["organizations"] = _as_str_list(document.get("organizations"))
    document["requires_validation"] = bool(document.get("requires_validation", False))
    document["channel_name"] = str(document.get("channel_name") or "")
    document["channel_username"] = str(document.get("channel_username") or "")
    document["channel_url"] = str(document.get("channel_url") or "")
    document["message_url"] = str(document.get("message_url") or document.get("source_url") or "")
    document["source_type"] = str(document.get("source_type") or "")
    document["cve_ids"] = _as_str_list(document.get("cve_ids"))
    document["detected_keywords"] = _as_str_list(document.get("detected_keywords"))
    document["intel_category"] = str(document.get("intel_category") or "")
    try:
        document["message_id"] = int(document.get("message_id") or 0)
    except (TypeError, ValueError):
        document["message_id"] = 0
    document["organization"] = str(document.get("organization") or UNKNOWN_LABEL)
    document["risk_category"] = str(document.get("risk_category") or UNKNOWN_LABEL)
    document["confidence"] = str(document.get("confidence") or UNKNOWN_LABEL)
    document["severity"] = str(document.get("severity") or UNKNOWN_LABEL)
    document["status"] = str(document.get("status") or UNKNOWN_LABEL)
    document["triage_status"] = str(document.get("triage_status") or document["status"])
    document["detection_category"] = str(document.get("detection_category") or document.get("category") or UNKNOWN_LABEL)
    document["final_decision"] = str(document.get("final_decision") or UNKNOWN_LABEL)
    document["noise_reason"] = str(document.get("noise_reason") or "")
    document["search_query_context"] = str(document.get("search_query_context") or "")
    document["review_note"] = str(document.get("review_note") or "")
    document["reviewed_by"] = str(document.get("reviewed_by") or UNKNOWN_LABEL)
    document["reviewed_at"] = str(document.get("reviewed_at") or "")
    document["collected_at"] = str(document.get("collected_at") or document.get("timestamp") or "")
    document["processed_at"] = str(document.get("processed_at") or "")
    document["content_evidence"] = _as_str_list(document.get("content_evidence"))
    document["evidence_lines"] = _as_str_list(document.get("evidence_lines"))
    document["evidence_excerpt"] = str(document.get("evidence_excerpt") or "")

    raw_line_numbers = document.get("evidence_line_numbers")
    if isinstance(raw_line_numbers, list):
        line_numbers: list[int] = []
        for value in raw_line_numbers:
            try:
                line_numbers.append(int(value))
            except (TypeError, ValueError):
                continue
        document["evidence_line_numbers"] = line_numbers
    else:
        document["evidence_line_numbers"] = []
    document["matched_watchlist"] = _as_str_list(document.get("matched_watchlist"))
    document["matched_emails"] = _as_str_list(document.get("matched_emails"))
    document["matched_domains"] = _as_str_list(document.get("matched_domains"))
    document["detected_indicators"] = _as_str_list(document.get("detected_indicators"))
    document["secret_types"] = _as_str_list(document.get("secret_types"))
    document["validation_reasons"] = _as_str_list(document.get("validation_reasons"))
    document["redacted_text"] = str(document.get("redacted_text") or "")
    document["is_noise"] = bool(document.get("is_noise", False))

    try:
        document["risk_score"] = int(document.get("risk_score") or 0)
    except (TypeError, ValueError):
        document["risk_score"] = 0

    for int_field in ("confidence_score", "extracted_secrets_count", "validated_secrets_count", "placeholder_count"):
        try:
            document[int_field] = int(document.get(int_field) or 0)
        except (TypeError, ValueError):
            document[int_field] = 0

    try:
        document["text_length"] = int(document.get("text_length") or 0)
    except (TypeError, ValueError):
        document["text_length"] = 0

    return document
