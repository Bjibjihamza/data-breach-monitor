from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import NotFoundError

from app.config import settings
from app.schemas.detection_review import ALLOWED_DETECTION_STATUSES
from app.storage.elastic_helpers import (
    UNKNOWN_LABEL,
    build_terms_aggregations,
    index_properties,
    normalize_detection_document,
    resolve_timeline_date_field,
    search_total,
    terms_aggregation_dict,
)


logger = logging.getLogger(__name__)

INDEX_NAME = "breach_signals"
COLLECTION_RUNS_INDEX = "collection_runs"
COLLECTION_STATE_INDEX = "collection_state"
DEFAULT_DETECTION_LIST_LIMIT = 50
MAX_DETECTION_LIST_LIMIT = 100
_MAX_CONNECT_RETRIES = 10
_INITIAL_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 8.0

_elasticsearch_ready = False


class ElasticsearchUnavailableError(RuntimeError):
    pass


class ElasticsearchQueryError(RuntimeError):
    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class DetectionNotFoundError(LookupError):
    def __init__(self, detection_hash: str) -> None:
        self.detection_hash = detection_hash
        super().__init__(f"Detection not found: {detection_hash}")


def wait_for_elasticsearch(
    *,
    max_retries: int = _MAX_CONNECT_RETRIES,
    initial_backoff_seconds: float = _INITIAL_BACKOFF_SECONDS,
    max_backoff_seconds: float = _MAX_BACKOFF_SECONDS,
) -> None:
    global _elasticsearch_ready
    if _elasticsearch_ready:
        return

    url = settings.ELASTICSEARCH_URL
    logger.info("Waiting for Elasticsearch...")
    backoff = initial_backoff_seconds

    for attempt in range(1, max_retries + 1):
        client = Elasticsearch(url)
        try:
            if client.ping():
                _elasticsearch_ready = True
                logger.info("Elasticsearch available.")
                return
        except Exception as exc:
            logger.debug("Elasticsearch ping failed on attempt %s: %s", attempt, exc.__class__.__name__)

        if attempt >= max_retries:
            break

        logger.warning(
            "Retrying Elasticsearch connection... (attempt %s/%s, next retry in %.1fs)",
            attempt,
            max_retries,
            backoff,
        )
        time.sleep(backoff)
        backoff = min(backoff * 2, max_backoff_seconds)

    message = (
        f"Elasticsearch unavailable at {url} after {max_retries} connection attempt(s). "
        "Ensure Elasticsearch is running and reachable."
    )
    logger.error(message)
    raise ElasticsearchUnavailableError(message)


def get_elastic_client() -> Elasticsearch:
    wait_for_elasticsearch()
    return Elasticsearch(settings.ELASTICSEARCH_URL)


def ensure_index() -> None:
    client = get_elastic_client()
    google_alerts_mapping = {
        "signal_type": {"type": "keyword"},
        "alert_name": {"type": "keyword"},
        "category": {"type": "keyword"},
        "country": {"type": "keyword"},
        "organizations": {"type": "keyword"},
        "matched_organization": {"type": "keyword"},
        "matched_organizations": {"type": "keyword"},
        "query": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 1024}}},
        "summary": {"type": "text"},
        "published_at": {"type": "date"},
        "requires_validation": {"type": "boolean"},
        "source_name": {"type": "keyword"},
        "source_reputation": {"type": "keyword"},
        "article_age_days": {"type": "integer"},
        "channel_name": {"type": "keyword"},
        "channel_username": {"type": "keyword"},
        "channel_url": {"type": "keyword"},
        "message_id": {"type": "long"},
        "message_url": {"type": "keyword"},
        "text": {"type": "text"},
        "source_type": {"type": "keyword"},
        "cve_ids": {"type": "keyword"},
        "detected_keywords": {"type": "keyword"},
        "intel_category": {"type": "keyword"},
    }
    if client.indices.exists(index=INDEX_NAME):
        properties = _index_properties(client)
        missing_properties = {
            field: mapping
            for field, mapping in google_alerts_mapping.items()
            if field not in properties
        }
        if missing_properties:
            client.indices.put_mapping(index=INDEX_NAME, properties=missing_properties)
        return

    mapping = {
        "mappings": {
            "properties": {
                "source": {"type": "keyword"},
                "source_url": {"type": "keyword"},
                "title": {"type": "text"},
                "organization": {"type": "keyword"},
                "risk_category": {"type": "keyword"},
                "confidence": {"type": "keyword"},
                "collected_at": {"type": "date"},
                "processed_at": {"type": "date"},
                "matched_emails": {"type": "keyword"},
                "matched_domains": {"type": "keyword"},
                "matched_watchlist": {"type": "keyword"},
                "detected_indicators": {"type": "keyword"},
                "redacted_text": {"type": "text"},
                "risk_score": {"type": "integer"},
                "severity": {"type": "keyword"},
                "detection_category": {"type": "keyword"},
                "is_noise": {"type": "boolean"},
                "noise_reason": {"type": "keyword"},
                "extracted_secrets_count": {"type": "integer"},
                "validated_secrets_count": {"type": "integer"},
                "placeholder_count": {"type": "integer"},
                "secret_types": {"type": "keyword"},
                "validation_reasons": {"type": "keyword"},
                "final_decision": {"type": "keyword"},
                "triage_status": {"type": "keyword"},
                "confidence_score": {"type": "integer"},
                "content_evidence": {"type": "keyword"},
                "evidence_lines": {"type": "keyword"},
                "evidence_line_numbers": {"type": "integer"},
                "evidence_excerpt": {"type": "text"},
                "search_query_context": {"type": "keyword"},
                "status": {"type": "keyword"},
                "review_note": {"type": "text"},
                "reviewed_by": {"type": "keyword"},
                "reviewed_at": {"type": "date"},
                "text_length": {"type": "integer"},
                "detection_hash": {"type": "keyword"},
                **google_alerts_mapping,
            }
        }
    }
    client.indices.create(index=INDEX_NAME, **mapping)


def ensure_collection_runs_index() -> None:
    client = get_elastic_client()
    properties = {
        "source": {"type": "keyword"},
        "run_id": {"type": "keyword"},
        "started_at": {"type": "date"},
        "ended_at": {"type": "date"},
        "duration_seconds": {"type": "float"},
        "status": {"type": "keyword"},
        "configured_items": {"type": "integer"},
        "processed_items": {"type": "integer"},
        "collected": {"type": "integer"},
        "indexed": {"type": "integer"},
        "duplicates_skipped": {"type": "integer"},
        "skipped_noise": {"type": "integer"},
        "skipped_informational": {"type": "integer"},
        "errors": {"type": "integer"},
        "message": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 512}}},
        "details": {"type": "object", "enabled": True},
    }
    if client.indices.exists(index=COLLECTION_RUNS_INDEX):
        try:
            mapping = client.indices.get_mapping(index=COLLECTION_RUNS_INDEX)
            existing = index_properties(mapping)
            missing = {field: mapping for field, mapping in properties.items() if field not in existing}
            if missing:
                client.indices.put_mapping(index=COLLECTION_RUNS_INDEX, properties=missing)
        except Exception as exc:
            logger.warning(
                "Unable to update collection_runs mapping: %s",
                exc.__class__.__name__,
            )
        return

    client.indices.create(
        index=COLLECTION_RUNS_INDEX,
        mappings={"properties": properties},
    )


def ensure_collection_state_index() -> None:
    client = get_elastic_client()
    properties = {
        "source": {"type": "keyword"},
        "key": {"type": "keyword"},
        "state": {"type": "object", "enabled": True},
        "updated_at": {"type": "date"},
    }
    if client.indices.exists(index=COLLECTION_STATE_INDEX):
        try:
            mapping = client.indices.get_mapping(index=COLLECTION_STATE_INDEX)
            existing = index_properties(mapping)
            missing = {field: mapping for field, mapping in properties.items() if field not in existing}
            if missing:
                client.indices.put_mapping(index=COLLECTION_STATE_INDEX, properties=missing)
        except Exception as exc:
            logger.warning("Unable to update collection_state mapping: %s", exc.__class__.__name__)
        return

    client.indices.create(index=COLLECTION_STATE_INDEX, mappings={"properties": properties})


def _collection_state_id(source: str, key: str) -> str:
    return f"{source}:{key}"


def get_collection_state(source: str, key: str) -> dict[str, Any]:
    try:
        ensure_collection_state_index()
        client = get_elastic_client()
        response = client.options(ignore_status=404).get(
            index=COLLECTION_STATE_INDEX,
            id=_collection_state_id(source, key),
        )
    except Exception as exc:
        logger.warning("Unable to read collection state source=%s key=%s: %s", source, key, exc.__class__.__name__)
        return {}
    if not response or not response.get("found"):
        return {}
    doc = response.get("_source") if isinstance(response.get("_source"), dict) else {}
    state = doc.get("state") if isinstance(doc.get("state"), dict) else {}
    return state


def save_collection_state(source: str, key: str, state: dict[str, Any]) -> dict[str, Any]:
    try:
        ensure_collection_state_index()
        client = get_elastic_client()
        updated_at = datetime.now(timezone.utc).isoformat()
        document = {
            "source": source,
            "key": key,
            "state": state if isinstance(state, dict) else {},
            "updated_at": updated_at,
        }
        response = client.index(
            index=COLLECTION_STATE_INDEX,
            id=_collection_state_id(source, key),
            document=document,
            refresh=True,
        )
        return {"index": COLLECTION_STATE_INDEX, "id": _collection_state_id(source, key), "result": response.get("result", "unknown")}
    except Exception as exc:
        logger.warning("Unable to save collection state source=%s key=%s: %s", source, key, exc.__class__.__name__)
        return {"index": COLLECTION_STATE_INDEX, "id": _collection_state_id(source, key), "result": "failed"}


def update_collection_state(source: str, key: str, partial_state: dict[str, Any]) -> dict[str, Any]:
    existing = get_collection_state(source, key)
    merged = {**existing, **(partial_state if isinstance(partial_state, dict) else {})}
    return save_collection_state(source, key, merged)


def list_collection_states(*, source: str | None = None, limit: int = 100) -> dict[str, Any]:
    client = get_elastic_client()
    normalized_limit = min(max(1, limit), 500)
    if not client.indices.exists(index=COLLECTION_STATE_INDEX):
        return {"total": 0, "states": []}
    query = {"term": {"source": source}} if source else {"match_all": {}}
    try:
        response = client.search(
            index=COLLECTION_STATE_INDEX,
            query=query,
            size=normalized_limit,
            sort=[{"updated_at": {"order": "desc", "unmapped_type": "date", "missing": "_last"}}],
        )
    except Exception as exc:
        logger.exception("Unable to list collection states: %s", exc)
        raise ElasticsearchQueryError(f"Elasticsearch search failed for collection_state: {exc}", cause=exc) from exc

    hits = response.get("hits") if isinstance(response.get("hits"), dict) else {}
    hit_list = hits.get("hits") if isinstance(hits.get("hits"), list) else []
    states: list[dict[str, Any]] = []
    for hit in hit_list:
        if not isinstance(hit, dict):
            continue
        doc = hit.get("_source")
        if not isinstance(doc, dict):
            continue
        state = doc.get("state") if isinstance(doc.get("state"), dict) else {}
        states.append(
            {
                "id": hit.get("_id"),
                "source": doc.get("source"),
                "key": doc.get("key"),
                "updated_at": doc.get("updated_at"),
                "state": state,
                **state,
            }
        )
    return {"total": search_total(hits), "states": states}


def _normalize_limit(limit: int) -> int:
    return min(max(1, limit), MAX_DETECTION_LIST_LIMIT)


def _index_properties(client: Elasticsearch) -> dict[str, Any]:
    try:
        if not client.indices.exists(index=INDEX_NAME):
            return {}
        mapping = client.indices.get_mapping(index=INDEX_NAME)
        return index_properties(mapping)
    except Exception as exc:
        logger.warning("Unable to read index mapping for %s: %s", INDEX_NAME, exc.__class__.__name__)
        return {}


def _execute_search(client: Elasticsearch, *, operation: str, **kwargs: Any) -> dict[str, Any]:
    try:
        return client.search(index=INDEX_NAME, **kwargs)
    except Exception as exc:
        logger.exception("Elasticsearch search failed for operation=%s index=%s", operation, INDEX_NAME)
        raise ElasticsearchQueryError(
            f"Elasticsearch search failed for {operation}: {exc}",
            cause=exc,
        ) from exc


def _empty_analytics_summary() -> dict[str, Any]:
    return {
        "total_detections": 0,
        "detections_by_source": {},
        "detections_by_signal_type": {},
        "detections_by_organization": {},
        "detections_by_category": {},
        "detections_by_country": {},
        "detections_by_risk_category": {},
        "detections_by_confidence": {},
        "detections_by_severity": {},
        "detections_by_status": {},
        "detections_by_final_decision": {},
        "detections_by_triage_status": {},
        "detections_by_secret_type": {},
        "latest_detections": [],
    }


def get_analytics_summary() -> dict[str, Any]:
    client = get_elastic_client()
    if not client.indices.exists(index=INDEX_NAME):
        return _empty_analytics_summary()

    properties = _index_properties(client)
    sort_field = resolve_timeline_date_field(properties) or "processed_at"
    search_kwargs: dict[str, Any] = {
        "query": {"match_all": {}},
        "size": 10,
        "sort": [{sort_field: {"order": "desc", "unmapped_type": "date", "missing": "_last"}}],
    }
    aggregations = build_terms_aggregations(properties)
    if aggregations:
        search_kwargs["aggs"] = aggregations

    try:
        response = _execute_search(client, operation="analytics_summary", **search_kwargs)
    except ElasticsearchQueryError:
        return _empty_analytics_summary()

    aggregations_result = response.get("aggregations") if isinstance(response.get("aggregations"), dict) else {}
    hits = response.get("hits") if isinstance(response.get("hits"), dict) else {}
    hit_list = hits.get("hits") if isinstance(hits.get("hits"), list) else []

    return {
        "total_detections": search_total(hits),
        "detections_by_source": terms_aggregation_dict(aggregations_result.get("by_source")),
        "detections_by_signal_type": terms_aggregation_dict(aggregations_result.get("by_signal_type")),
        "detections_by_organization": terms_aggregation_dict(aggregations_result.get("by_organization")),
        "detections_by_category": terms_aggregation_dict(aggregations_result.get("by_category")),
        "detections_by_country": terms_aggregation_dict(aggregations_result.get("by_country")),
        "detections_by_risk_category": terms_aggregation_dict(aggregations_result.get("by_risk_category")),
        "detections_by_confidence": terms_aggregation_dict(aggregations_result.get("by_confidence")),
        "detections_by_severity": terms_aggregation_dict(aggregations_result.get("by_severity")),
        "detections_by_status": terms_aggregation_dict(aggregations_result.get("by_status")),
        "detections_by_final_decision": terms_aggregation_dict(
            aggregations_result.get("by_final_decision")
        ),
        "detections_by_triage_status": terms_aggregation_dict(
            aggregations_result.get("by_triage_status")
        ),
        "detections_by_secret_type": terms_aggregation_dict(aggregations_result.get("by_secret_type")),
        "latest_detections": [normalize_detection_document(hit) for hit in hit_list if isinstance(hit, dict)],
    }


def get_analytics_timeline(
    *,
    interval: Literal["hour", "day"],
    days: int = 7,
) -> dict[str, Any]:
    client = get_elastic_client()
    normalized_days = min(max(1, days), 90)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=normalized_days)
    calendar_interval = "1h" if interval == "hour" else "1d"

    if not client.indices.exists(index=INDEX_NAME):
        return {"interval": interval, "days": normalized_days, "points": []}

    properties = _index_properties(client)
    date_field = resolve_timeline_date_field(properties)
    if date_field is None:
        logger.warning("No date field available for analytics timeline on index %s.", INDEX_NAME)
        return {"interval": interval, "days": normalized_days, "points": []}

    try:
        response = _execute_search(
            client,
            operation="analytics_timeline",
            size=0,
            query={
                "range": {
                    date_field: {
                        "gte": start.isoformat(),
                        "lte": now.isoformat(),
                    }
                }
            },
            aggs={
                "detections_over_time": {
                    "date_histogram": {
                        "field": date_field,
                        "calendar_interval": calendar_interval,
                        "min_doc_count": 0,
                        "extended_bounds": {
                            "min": start.isoformat(),
                            "max": now.isoformat(),
                        },
                    }
                }
            },
        )
    except ElasticsearchQueryError:
        return {"interval": interval, "days": normalized_days, "points": []}

    histogram = response.get("aggregations", {}).get("detections_over_time", {})
    buckets = histogram.get("buckets") if isinstance(histogram, dict) else []
    if not isinstance(buckets, list):
        buckets = []

    points = []
    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        points.append(
            {
                "timestamp": str(bucket.get("key_as_string") or bucket.get("key") or UNKNOWN_LABEL),
                "count": int(bucket.get("doc_count", 0)),
            }
        )
    return {"interval": interval, "days": normalized_days, "points": points}


def _build_detection_query(
    *,
    source: str | None = None,
    signal_type: str | None = None,
    organization: str | None = None,
    category: str | None = None,
    country: str | None = None,
    risk_category: str | None = None,
    confidence: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    search: str | None = None,
    date_range: str | None = None,
    date_field: str = "processed_at",
) -> dict[str, Any]:
    filters: list[dict[str, Any]] = []
    for field, value in (
        ("source", source),
        ("signal_type", signal_type),
        ("category", category),
        ("country", country),
        ("risk_category", risk_category),
        ("confidence", confidence),
        ("severity", severity),
        ("status", status),
    ):
        if value:
            filters.append({"term": {field: value}})

    if organization:
        filters.append(
            {
                "bool": {
                    "should": [
                        {"term": {"organization": organization}},
                        {"term": {"matched_organization": organization}},
                        {"term": {"matched_organizations": organization}},
                        {"term": {"organizations": organization}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )

    if date_range and date_range != "all":
        range_start_by_key = {
            "1h": "now-1h",
            "24h": "now-24h",
            "7d": "now-7d",
            "30d": "now-30d",
        }
        range_start = range_start_by_key.get(date_range)
        if range_start:
            filters.append({"range": {date_field: {"gte": range_start, "lte": "now"}}})

    must: list[dict[str, Any]] = []
    if search:
        must.append(
            {
                "simple_query_string": {
                    "query": search,
                    "fields": [
                        "title^3",
                        "organization^2",
                        "matched_organization^2",
                        "matched_organizations^2",
                        "organizations^2",
                        "source_url",
                        "message_url",
                        "redacted_text",
                        "evidence_excerpt",
                        "summary",
                        "text",
                        "cve_ids",
                        "detection_hash",
                        "alert_name",
                        "channel_name",
                        "channel_username",
                        "detected_keywords",
                        "secret_types",
                        "risk_category",
                    ],
                    "default_operator": "and",
                }
            }
        )

    if filters or must:
        query = {"bool": {}}
        if filters:
            query["bool"]["filter"] = filters
        if must:
            query["bool"]["must"] = must
    else:
        return {"match_all": {}}

    return query


def list_detections(
    *,
    source: str | None = None,
    signal_type: str | None = None,
    organization: str | None = None,
    category: str | None = None,
    country: str | None = None,
    risk_category: str | None = None,
    confidence: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    search: str | None = None,
    date_range: str | None = None,
    offset: int = 0,
    limit: int = DEFAULT_DETECTION_LIST_LIMIT,
) -> dict[str, Any]:
    client = get_elastic_client()
    normalized_limit = _normalize_limit(limit)
    normalized_offset = max(0, offset)

    if not client.indices.exists(index=INDEX_NAME):
        return {"total": 0, "limit": normalized_limit, "offset": normalized_offset, "detections": []}

    properties = _index_properties(client)
    sort_field = resolve_timeline_date_field(properties) or "processed_at"
    query = _build_detection_query(
        source=source,
        signal_type=signal_type,
        organization=organization,
        category=category,
        country=country,
        risk_category=risk_category,
        confidence=confidence,
        severity=severity,
        status=status,
        search=search,
        date_range=date_range,
        date_field=sort_field,
    )

    try:
        response = _execute_search(
            client,
            operation="list_detections",
            query=query,
            from_=normalized_offset,
            size=normalized_limit,
            sort=[{sort_field: {"order": "desc", "unmapped_type": "date", "missing": "_last"}}],
        )
    except ElasticsearchQueryError:
        return {"total": 0, "limit": normalized_limit, "offset": normalized_offset, "detections": []}

    hits = response.get("hits") if isinstance(response.get("hits"), dict) else {}
    hit_list = hits.get("hits") if isinstance(hits.get("hits"), list) else []
    detections = [
        normalize_detection_document(hit) for hit in hit_list if isinstance(hit, dict)
    ]
    return {
        "total": search_total(hits),
        "limit": normalized_limit,
        "offset": normalized_offset,
        "detections": detections,
    }


def get_latest_detection_for_source(source: str) -> dict[str, Any] | None:
    result = list_detections(source=source, limit=1)
    detections = result.get("detections")
    if isinstance(detections, list) and detections:
        detection = detections[0]
        return detection if isinstance(detection, dict) else None
    return None


def get_analytics_charts(
    *,
    source: str | None = None,
    signal_type: str | None = None,
    organization: str | None = None,
    category: str | None = None,
    country: str | None = None,
    risk_category: str | None = None,
    confidence: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    search: str | None = None,
    date_range: str | None = None,
) -> dict[str, Any]:
    client = get_elastic_client()
    if not client.indices.exists(index=INDEX_NAME):
        return {
            "total": 0,
            "terms": _empty_chart_terms(),
            "timeline": [],
            "telegram_cve_timeline": [],
            "google_alerts_timeline": [],
        }

    properties = _index_properties(client)
    date_field = resolve_timeline_date_field(properties)
    query = _build_detection_query(
        source=source,
        signal_type=signal_type,
        organization=organization,
        category=category,
        country=country,
        risk_category=risk_category,
        confidence=confidence,
        severity=severity,
        status=status,
        search=search,
        date_range=date_range if date_field else None,
        date_field=date_field or "processed_at",
    )

    aggs: dict[str, Any] = build_terms_aggregations(properties)
    if date_field:
        aggs["timeline"] = {
            "date_histogram": {
                "field": date_field,
                "calendar_interval": "1d",
                "min_doc_count": 0,
            }
        }
        aggs["telegram_cve_timeline"] = {
            "filter": {"bool": {"filter": [{"term": {"source": "telegram"}}, {"exists": {"field": "cve_ids"}}]}},
            "aggs": {
                "points": {
                    "date_histogram": {
                        "field": date_field,
                        "calendar_interval": "1d",
                        "min_doc_count": 0,
                    }
                }
            },
        }
        aggs["google_alerts_timeline"] = {
            "filter": {"term": {"source": "google_alerts"}},
            "aggs": {
                "points": {
                    "date_histogram": {
                        "field": date_field,
                        "calendar_interval": "1d",
                        "min_doc_count": 0,
                    }
                }
            },
        }

    try:
        response = _execute_search(
            client,
            operation="analytics_charts",
            query=query,
            size=0,
            aggs=aggs,
        )
    except ElasticsearchQueryError:
        return {
            "total": 0,
            "terms": _empty_chart_terms(),
            "timeline": [],
            "telegram_cve_timeline": [],
            "google_alerts_timeline": [],
        }

    aggregations = response.get("aggregations") if isinstance(response.get("aggregations"), dict) else {}
    hits = response.get("hits") if isinstance(response.get("hits"), dict) else {}

    def _histogram_points(aggregation: dict[str, Any] | None) -> list[dict[str, Any]]:
        buckets = aggregation.get("buckets") if isinstance(aggregation, dict) else []
        if not isinstance(buckets, list):
            return []
        return [
            {"timestamp": str(bucket.get("key_as_string") or bucket.get("key") or UNKNOWN_LABEL), "count": int(bucket.get("doc_count", 0))}
            for bucket in buckets
            if isinstance(bucket, dict)
        ]

    return {
        "total": search_total(hits),
        "terms": {
            **_empty_chart_terms(),
            "source": terms_aggregation_dict(aggregations.get("by_source")),
            "signal_type": terms_aggregation_dict(aggregations.get("by_signal_type")),
            "organization": terms_aggregation_dict(aggregations.get("by_organization")),
            "category": terms_aggregation_dict(aggregations.get("by_category")),
            "country": terms_aggregation_dict(aggregations.get("by_country")),
            "risk_category": terms_aggregation_dict(aggregations.get("by_risk_category")),
            "confidence": terms_aggregation_dict(aggregations.get("by_confidence")),
            "severity": terms_aggregation_dict(aggregations.get("by_severity")),
            "status": terms_aggregation_dict(aggregations.get("by_status")),
            "secret_type": terms_aggregation_dict(aggregations.get("by_secret_type")),
        },
        "timeline": _histogram_points(aggregations.get("timeline")),
        "telegram_cve_timeline": _histogram_points(
            aggregations.get("telegram_cve_timeline", {}).get("points")
            if isinstance(aggregations.get("telegram_cve_timeline"), dict)
            else None
        ),
        "google_alerts_timeline": _histogram_points(
            aggregations.get("google_alerts_timeline", {}).get("points")
            if isinstance(aggregations.get("google_alerts_timeline"), dict)
            else None
        ),
    }


def _empty_chart_terms() -> dict[str, dict[str, int]]:
    return {
        "source": {},
        "severity": {},
        "confidence": {},
        "status": {},
        "organization": {},
        "risk_category": {},
        "secret_type": {},
    }


def _scan_run_status(result: dict[str, Any]) -> str:
    if result.get("status") in {"success", "warning", "error", "failed"}:
        return "error" if result.get("status") == "failed" else str(result["status"])
    if result.get("error") == "elasticsearch_unavailable":
        return "error"
    errors = int(result.get("errors") or 0)
    if errors:
        return "warning"
    if result.get("config_error") or result.get("error"):
        return "warning"
    if result.get("source") == "google_alerts" and int(result.get("valid_rss_urls") or 0) == 0:
        return "warning"
    return "success"


def _scan_run_message(result: dict[str, Any]) -> str:
    if result.get("message"):
        return str(result["message"])
    if result.get("error"):
        return str(result["error"])
    if result.get("config_error"):
        return str(result["config_error"])
    if result.get("source") == "google_alerts" and int(result.get("valid_rss_urls") or 0) == 0:
        return "no feeds loaded"
    source = str(result.get("source") or "scan")
    indexed = int(result.get("indexed") or result.get("saved") or 0)
    collected = int(result.get("collected") or result.get("messages_collected") or 0)
    errors = int(result.get("errors") or 0)
    if errors:
        return f"{source} completed with {errors} error(s)"
    if collected == 0 and indexed == 0:
        return "no data collected"
    return "success"


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def save_scan_run_summary(source: str, result: dict[str, Any]) -> dict[str, Any]:
    try:
        ensure_collection_runs_index()
        client = get_elastic_client()
    except Exception as exc:
        logger.warning("Unable to prepare collection run summary index for %s: %s", source, exc.__class__.__name__)
        return {"index": COLLECTION_RUNS_INDEX, "id": "", "result": "failed"}

    ended_dt = _parse_datetime(result.get("ended_at")) or datetime.now(timezone.utc)
    started_dt = _parse_datetime(result.get("started_at")) or ended_dt
    ended_at = ended_dt.isoformat()
    started_at = started_dt.isoformat()
    duration_seconds = max(0.0, (ended_dt - started_dt).total_seconds())
    indexed = int(result.get("indexed") or result.get("saved") or 0)
    collected = int(result.get("collected") or result.get("messages_collected") or 0)
    duplicates = int(result.get("duplicates_skipped") or 0)
    errors = int(result.get("errors") or 0)
    status = _scan_run_status(result)
    run_id = str(result.get("run_id") or f"{source}:{ended_dt.timestamp()}:{uuid4().hex[:8]}")
    document = {
        "run_id": run_id,
        "source": source,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": duration_seconds,
        "status": status,
        "configured_items": int(result.get("configured_items") or 0),
        "processed_items": int(result.get("processed_items") or 0),
        "collected": collected,
        "indexed": indexed,
        "duplicates_skipped": duplicates,
        "skipped_noise": int(result.get("skipped_noise") or 0),
        "skipped_informational": int(result.get("skipped_informational") or 0),
        "errors": errors,
        "message": _scan_run_message(result),
        "details": result.get("details") if isinstance(result.get("details"), dict) else {},
    }
    try:
        response = client.index(index=COLLECTION_RUNS_INDEX, id=run_id, document=document, refresh=True)
    except Exception as exc:
        logger.warning("Unable to persist collection run summary for %s: %s", source, exc.__class__.__name__)
        return {"index": COLLECTION_RUNS_INDEX, "id": run_id, "result": "failed"}
    return {"index": COLLECTION_RUNS_INDEX, "id": run_id, "result": response.get("result", "unknown")}


def list_collection_runs(
    *,
    source: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    client = get_elastic_client()
    normalized_limit = min(max(1, limit), 100)
    if not client.indices.exists(index=COLLECTION_RUNS_INDEX):
        return {"total": 0, "runs": []}

    filters: list[dict[str, Any]] = []
    if source:
        filters.append({"term": {"source": source}})
    if status:
        filters.append({"term": {"status": status}})
    query = {"bool": {"filter": filters}} if filters else {"match_all": {}}
    try:
        response = client.search(
            index=COLLECTION_RUNS_INDEX,
            query=query,
            size=normalized_limit,
            sort=[{"ended_at": {"order": "desc", "unmapped_type": "date", "missing": "_last"}}],
        )
    except Exception as exc:
        logger.exception("Unable to list collection runs: %s", exc)
        raise ElasticsearchQueryError(f"Elasticsearch search failed for collection_runs: {exc}", cause=exc) from exc

    hits = response.get("hits") if isinstance(response.get("hits"), dict) else {}
    hit_list = hits.get("hits") if isinstance(hits.get("hits"), list) else []
    runs: list[dict[str, Any]] = []
    for hit in hit_list:
        if not isinstance(hit, dict):
            continue
        doc = hit.get("_source")
        if isinstance(doc, dict):
            runs.append({"id": hit.get("_id"), **doc})
    return {"total": search_total(hits), "runs": runs}


def _source_health_from_run(source: str, name: str, enabled: bool, run: dict[str, Any]) -> dict[str, object]:
    source_doc = run.get("_source", run)
    if not isinstance(source_doc, dict):
        source_doc = {}
    run_status = str(source_doc.get("status") or "unknown")
    errors = int(source_doc.get("errors") or 0)
    duplicates = int(source_doc.get("duplicates_skipped") or 0)
    indexed = int(source_doc.get("indexed") or 0)
    collected = int(source_doc.get("collected") or 0)
    skipped_noise = int(source_doc.get("skipped_noise") or 0)
    skipped_informational = int(source_doc.get("skipped_informational") or 0)
    details = source_doc.get("details") if isinstance(source_doc.get("details"), dict) else {}

    warning_count = 0
    warning_reasons: list[str] = []
    if details.get("rate_limited") or details.get("rate_limit_detected"):
        warning_count += 1
        warning_reasons.append("rate limit reached")
    if source == "github" and details.get("rotated") is False:
        warning_count += 1
        warning_reasons.append("query rotation did not advance")
    if errors > 0:
        warning_count += errors
        warning_reasons.append(f"{errors} collector error(s)")

    if not enabled:
        health_status = "disabled"
        scan_result = "skipped"
    elif run_status == "error":
        health_status = "error"
        scan_result = "failed"
    elif errors > 0 or warning_count > 0 or run_status == "warning":
        health_status = "warning"
        scan_result = "partial"
    elif run_status == "success":
        health_status = "healthy"
        scan_result = "completed"
    else:
        health_status = "unknown"
        scan_result = run_status

    base_message = str(source_doc.get("message") or run_status)
    if health_status == "healthy" and indexed == 0:
        if duplicates > 0 and collected > 0:
            message = f"{name} scan completed successfully. Only duplicate detections were found."
        elif skipped_noise > 0 or skipped_informational > 0:
            message = f"{name} scan completed successfully. Signals were filtered by the detection policy; no new validated detections were indexed."
        else:
            message = f"{name} scan completed successfully. No new validated detections were indexed."
    elif warning_reasons:
        message = f"{base_message}. Warnings: {', '.join(warning_reasons)}."
    else:
        message = base_message

    last_scan_at = source_doc.get("ended_at") or source_doc.get("started_at") or "unknown"
    return {
        "source": source,
        "name": name,
        "status": health_status,
        "enabled": enabled,
        "scan_result": scan_result,
        "last_scan_at": last_scan_at,
        "last_scan_time": last_scan_at,
        "last_scan_status": run_status,
        "last_scan_result": scan_result,
        "message": message,
        "last_message": message,
        "indexed_count": indexed,
        "duplicate_count": duplicates,
        "error_count": errors,
        "warning_count": warning_count,
        "last_error": str(source_doc.get("error") or "") if errors or run_status == "error" else "",
        "last_indexed": indexed,
        "last_duplicates": duplicates,
        "last_errors": errors,
        "indexed_last_scan": indexed,
        "duplicates_skipped": duplicates,
        "errors": errors,
        "warnings": warning_count,
    }


def _latest_run_for_source(client: Elasticsearch, source: str) -> dict[str, Any] | None:
    if not client.indices.exists(index=COLLECTION_RUNS_INDEX):
        return None
    try:
        response = client.search(
            index=COLLECTION_RUNS_INDEX,
            query={"term": {"source": source}},
            size=1,
            sort=[{"ended_at": {"order": "desc", "unmapped_type": "date", "missing": "_last"}}],
        )
    except Exception as exc:
        logger.warning("Unable to read latest scan run for %s: %s", source, exc.__class__.__name__)
        return None
    hits = response.get("hits", {}).get("hits", [])
    if isinstance(hits, list) and hits:
        first = hits[0]
        return first if isinstance(first, dict) else None
    return None


def _recent_runs_for_source(client: Elasticsearch, source: str, *, limit: int = 3) -> list[dict[str, Any]]:
    if not client.indices.exists(index=COLLECTION_RUNS_INDEX):
        return []
    try:
        response = client.search(
            index=COLLECTION_RUNS_INDEX,
            query={"term": {"source": source}},
            size=limit,
            sort=[{"ended_at": {"order": "desc", "unmapped_type": "date", "missing": "_last"}}],
        )
    except Exception as exc:
        logger.warning("Unable to read recent scan runs for %s: %s", source, exc.__class__.__name__)
        return []
    hits = response.get("hits", {}).get("hits", [])
    return [hit for hit in hits if isinstance(hit, dict)] if isinstance(hits, list) else []


def get_source_health(sources: list[tuple[str, str, bool]]) -> dict[str, object]:
    client = get_elastic_client()
    entries: list[dict[str, object]] = []
    for source, name, enabled in sources:
        latest_run = _latest_run_for_source(client, source)
        if latest_run is not None:
            entry = _source_health_from_run(source, name, enabled, latest_run)
            if source == "github":
                recent_runs = _recent_runs_for_source(client, source, limit=3)
                windows = []
                for run in recent_runs:
                    doc = run.get("_source") if isinstance(run.get("_source"), dict) else {}
                    details = doc.get("details") if isinstance(doc.get("details"), dict) else {}
                    windows.append((details.get("query_window_start"), details.get("query_window_end")))
                if len(windows) >= 3 and len(set(windows)) == 1 and windows[0] != (None, None):
                    entry["status"] = "warning"
                    entry["scan_result"] = "partial"
                    entry["warning_count"] = int(entry.get("warning_count") or 0) + 1
                    entry["warnings"] = entry["warning_count"]
                    entry["message"] = "GitHub query window repeated across recent scans"
                    entry["last_message"] = entry["message"]
                    entry["last_scan_result"] = entry["scan_result"]
            entries.append(entry)
            continue

        entries.append(
            {
                "source": source,
                "name": name,
                "status": "unknown" if enabled else "disabled",
                "enabled": enabled,
                "scan_result": "unknown" if enabled else "skipped",
                "last_scan_at": "unknown",
                "last_scan_time": "unknown",
                "last_scan_status": "unknown",
                "last_scan_result": "unknown" if enabled else "skipped",
                "message": "unknown" if enabled else "source disabled",
                "last_message": "unknown" if enabled else "source disabled",
                "indexed_count": 0,
                "duplicate_count": 0,
                "error_count": 0,
                "warning_count": 0,
                "last_error": "",
                "last_indexed": 0,
                "last_duplicates": 0,
                "last_errors": 0,
                "indexed_last_scan": 0,
                "duplicates_skipped": 0,
                "errors": 0,
                "warnings": 0,
            }
        )
    return {"sources": entries}


def update_detection_status(
    detection_hash: str,
    *,
    status: str,
    review_note: str | None = None,
    reviewed_by: str | None = None,
) -> dict[str, Any]:
    if status not in ALLOWED_DETECTION_STATUSES:
        raise ValueError(f"Invalid status: {status}")

    client = get_elastic_client()
    if not client.indices.exists(index=INDEX_NAME):
        raise DetectionNotFoundError(detection_hash)

    document_id = detection_hash
    try:
        client.get(index=INDEX_NAME, id=detection_hash)
    except NotFoundError:
        response = _execute_search(
            client,
            operation="find_detection_for_status_update",
            query={"term": {"detection_hash": detection_hash}},
            size=1,
        )
        hits = response.get("hits", {}).get("hits", [])
        if not isinstance(hits, list) or not hits:
            raise DetectionNotFoundError(detection_hash) from None
        document_id = str(hits[0].get("_id") or detection_hash)

    update_doc: dict[str, Any] = {
        "status": status,
        "triage_status": status,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    if review_note is not None:
        update_doc["review_note"] = review_note
    if reviewed_by is not None:
        update_doc["reviewed_by"] = reviewed_by

    client.update(index=INDEX_NAME, id=document_id, doc=update_doc, refresh=True)
    updated = client.get(index=INDEX_NAME, id=document_id)
    return normalize_detection_document(updated)


def save_detection(detection: dict[str, object]) -> dict[str, object]:
    ensure_index()
    client = get_elastic_client()
    document_id = str(detection["detection_hash"])
    response = client.index(index=INDEX_NAME, id=document_id, document=detection)
    return {
        "index": INDEX_NAME,
        "id": document_id,
        "result": response.get("result", "unknown"),
    }


def detection_exists(detection_hash: str) -> bool:
    ensure_index()
    client = get_elastic_client()
    return bool(client.exists(index=INDEX_NAME, id=detection_hash))


def detection_exists_by_source_url(source_url: str) -> bool:
    """Return True if any detection with the given ``source_url`` is indexed.

    Used by collectors to skip remote content fetches / re-processing for items
    that are already known. Failures fall back to ``False`` so a transient
    Elasticsearch hiccup never blocks a scan.
    """

    if not source_url:
        return False
    try:
        client = get_elastic_client()
        if not client.indices.exists(index=INDEX_NAME):
            return False
        response = client.count(
            index=INDEX_NAME,
            query={"term": {"source_url": source_url}},
        )
        return int(response.get("count", 0)) > 0
    except Exception as exc:
        logger.debug(
            "detection_exists_by_source_url failed for %s: %s",
            source_url,
            exc.__class__.__name__,
        )
        return False


def detection_exists_by_telegram_message(channel_username: str, message_id: int | str) -> bool:
    """Return True if a Telegram detection with the same ``channel_username``
    and ``message_id`` is already indexed.
    """

    username = (channel_username or "").lstrip("@").strip()
    try:
        msg_id_int = int(message_id)
    except (TypeError, ValueError):
        return False
    if not username or msg_id_int <= 0:
        return False
    try:
        client = get_elastic_client()
        if not client.indices.exists(index=INDEX_NAME):
            return False
        response = client.count(
            index=INDEX_NAME,
            query={
                "bool": {
                    "filter": [
                        {"term": {"source": "telegram"}},
                        {"term": {"channel_username": username}},
                        {"term": {"message_id": msg_id_int}},
                    ]
                }
            },
        )
        return int(response.get("count", 0)) > 0
    except Exception as exc:
        logger.debug(
            "detection_exists_by_telegram_message failed for %s/%s: %s",
            username,
            message_id,
            exc.__class__.__name__,
        )
        return False


def upsert_collection_state(source: str, key: str, data: dict[str, Any]) -> dict[str, Any]:
    """Alias for :func:`update_collection_state` matching the project spec."""

    return update_collection_state(source, key, data)


def delete_mock_paste_detections() -> dict[str, int | str]:
    client = get_elastic_client()
    if not client.indices.exists(index=INDEX_NAME):
        return {"index": INDEX_NAME, "deleted": 0}

    response = client.delete_by_query(
        index=INDEX_NAME,
        query={"term": {"source": "mock_paste"}},
        conflicts="proceed",
        refresh=True,
    )
    return {"index": INDEX_NAME, "deleted": int(response.get("deleted", 0))}
