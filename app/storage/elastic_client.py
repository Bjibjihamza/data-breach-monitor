from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import BadRequestError, NotFoundError
from elasticsearch.helpers import scan

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
LATEST_SCAN_SOURCES = ("github", "google_alerts", "telegram")
DEFAULT_DETECTION_LIST_LIMIT = 50
MAX_DETECTION_LIST_LIMIT = 100
_MAX_CONNECT_RETRIES = 10
_INITIAL_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 8.0

_elasticsearch_ready = False


def _elasticsearch_error_body(exc: Exception) -> Any:
    for attr in ("body", "info"):
        value = getattr(exc, attr, None)
        if value:
            return value
    return str(exc)


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


def _resource_already_exists(exc: BadRequestError) -> bool:
    try:
        body = exc.body
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                return str(error.get("type") or "") == "resource_already_exists_exception"
    except Exception:
        pass
    return "resource_already_exists_exception" in str(exc)


def _safe_create_index(client: Elasticsearch, index: str, **kwargs: Any) -> None:
    if client.indices.exists(index=index):
        return
    try:
        client.indices.create(index=index, **kwargs)
    except BadRequestError as exc:
        if _resource_already_exists(exc):
            logger.info("Elasticsearch index %s already exists (race during create).", index)
            return
        raise


def ensure_index() -> None:
    client = get_elastic_client()
    google_alerts_mapping = {
        "run_id": {"type": "keyword"},
        "scan_group_id": {"type": "keyword"},
        "scan_started_at": {"type": "date"},
        "mode_requested": {"type": "keyword"},
        "effective_mode": {"type": "keyword"},
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
    _safe_create_index(client, INDEX_NAME, **mapping)


def ensure_collection_runs_index() -> None:
    client = get_elastic_client()
    properties = {
        "source": {"type": "keyword"},
        "run_id": {"type": "keyword"},
        "scan_group_id": {"type": "keyword"},
        "mode_requested": {"type": "keyword"},
        "effective_mode": {"type": "keyword"},
        "requested_scan_mode": {"type": "keyword"},
        "scan_mode": {"type": "keyword"},
        "started_at": {"type": "date"},
        "ended_at": {"type": "date"},
        "duration_seconds": {"type": "float"},
        "status": {"type": "keyword"},
        "configured_items": {"type": "integer"},
        "processed_items": {"type": "integer"},
        "collected": {"type": "integer"},
        "indexed": {"type": "integer"},
        "duplicates_skipped": {"type": "integer"},
        "skipped_existing": {"type": "integer"},
        "skipped_noise": {"type": "integer"},
        "skipped_informational": {"type": "integer"},
        "total_seen": {"type": "integer"},
        "last_cursor": {"type": "keyword", "ignore_above": 2048},
        "rate_limit_detected": {"type": "boolean"},
        "stopped_reason": {"type": "keyword", "ignore_above": 512},
        "local_export_enabled": {"type": "boolean"},
        "local_export_received": {"type": "integer"},
        "local_export_appended": {"type": "integer"},
        "local_export_skipped_existing": {"type": "integer"},
        "local_export_file": {"type": "keyword", "ignore_above": 2048},
        "errors": {"type": "integer"},
        "message": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 512}}},
        "details": {"type": "object", "enabled": False},
    }
    if client.indices.exists(index=COLLECTION_RUNS_INDEX):
        try:
            mapping = client.indices.get_mapping(index=COLLECTION_RUNS_INDEX)
            existing = index_properties(mapping)
            if not _collection_runs_details_mapping_is_disabled(existing):
                _recreate_collection_runs_index(client, properties)
                return
            missing = {field: mapping for field, mapping in properties.items() if field not in existing}
            if missing:
                client.indices.put_mapping(index=COLLECTION_RUNS_INDEX, properties=missing)
            _backfill_collection_run_documents(client)
        except Exception as exc:
            logger.warning(
                "Unable to update collection_runs mapping: %s",
                _elasticsearch_error_body(exc),
            )
        return

    _safe_create_index(
        client,
        COLLECTION_RUNS_INDEX,
        mappings={"properties": properties},
    )


def _collection_runs_details_mapping_is_disabled(properties: dict[str, Any]) -> bool:
    details = properties.get("details")
    return isinstance(details, dict) and details.get("enabled") is False


def _recreate_collection_runs_index(client: Elasticsearch, properties: dict[str, Any]) -> None:
    documents: list[dict[str, Any]] = []
    for hit in scan(
        client,
        index=COLLECTION_RUNS_INDEX,
        query={"query": {"match_all": {}}},
        preserve_order=False,
    ):
        if not isinstance(hit, dict):
            continue
        source = hit.get("_source")
        if not isinstance(source, dict):
            continue
        documents.append({"id": str(hit.get("_id") or source.get("run_id") or uuid4().hex), "document": source})

    client.indices.delete(index=COLLECTION_RUNS_INDEX)
    _safe_create_index(client, COLLECTION_RUNS_INDEX, mappings={"properties": properties})
    for item in documents:
        client.index(
            index=COLLECTION_RUNS_INDEX,
            id=item["id"],
            document=_normalize_collection_run_document(item["document"]),
        )
    if documents:
        client.indices.refresh(index=COLLECTION_RUNS_INDEX)
    logger.info(
        "Recreated %s with details.enabled=false and reindexed %s run summary document(s).",
        COLLECTION_RUNS_INDEX,
        len(documents),
    )


def _backfill_collection_run_documents(client: Elasticsearch) -> None:
    normalized_count = 0
    stable_fields = {
        "skipped_existing",
        "total_seen",
        "last_cursor",
        "rate_limit_detected",
        "stopped_reason",
        "local_export_enabled",
        "local_export_received",
        "local_export_appended",
        "local_export_skipped_existing",
        "local_export_file",
    }
    for hit in scan(
        client,
        index=COLLECTION_RUNS_INDEX,
        query={"query": {"match_all": {}}},
        preserve_order=False,
    ):
        if not isinstance(hit, dict):
            continue
        document = hit.get("_source")
        if not isinstance(document, dict):
            continue
        if stable_fields.issubset(document.keys()):
            continue
        document_id = str(hit.get("_id") or document.get("run_id") or uuid4().hex)
        client.index(
            index=COLLECTION_RUNS_INDEX,
            id=document_id,
            document=_normalize_collection_run_document(document),
        )
        normalized_count += 1
    if normalized_count:
        client.indices.refresh(index=COLLECTION_RUNS_INDEX)
        logger.info("Normalized %s existing collection run summary document(s).", normalized_count)


def _collection_run_details(document: dict[str, Any]) -> dict[str, Any]:
    details = document.get("details")
    return details if isinstance(details, dict) else {}


def _collection_run_total_seen(document: dict[str, Any], details: dict[str, Any]) -> int:
    if document.get("total_seen") is not None:
        return _safe_int(document.get("total_seen"))
    source = str(document.get("source") or "")
    if source == "github":
        return _safe_int(details.get("results_seen"))
    if source == "google_alerts":
        return _safe_int(details.get("rss_entries_collected")) + _safe_int(details.get("skipped_existing"))
    if source == "telegram":
        return (
            _safe_int(details.get("messages_collected"))
            + _safe_int(details.get("messages_already_known"))
            + _safe_int(details.get("skipped_existing"))
        )
    return _safe_int(document.get("collected")) + _safe_int(details.get("skipped_existing"))


def _normalize_collection_run_document(document: dict[str, Any]) -> dict[str, Any]:
    details = _collection_run_details(document)
    run_id = str(document.get("run_id") or uuid4().hex)
    scan_mode = str(document.get("scan_mode") or document.get("effective_mode") or details.get("scan_mode") or "")
    requested_scan_mode = str(
        document.get("requested_scan_mode") or document.get("mode_requested") or details.get("requested_scan_mode") or scan_mode
    )
    local_export = document.get("local_export")
    if not isinstance(local_export, dict):
        local_export = details.get("local_export") if isinstance(details.get("local_export"), dict) else {}
    return {
        "run_id": run_id,
        "scan_group_id": str(document.get("scan_group_id") or details.get("scan_group_id") or run_id),
        "source": str(document.get("source") or ""),
        "mode_requested": requested_scan_mode,
        "effective_mode": str(document.get("effective_mode") or details.get("effective_mode") or scan_mode or requested_scan_mode),
        "requested_scan_mode": requested_scan_mode,
        "scan_mode": scan_mode,
        "started_at": str(document.get("started_at") or document.get("ended_at") or datetime.now(timezone.utc).isoformat()),
        "ended_at": str(document.get("ended_at") or document.get("started_at") or datetime.now(timezone.utc).isoformat()),
        "duration_seconds": float(document.get("duration_seconds") or 0.0),
        "status": str(document.get("status") or "unknown"),
        "configured_items": _safe_int(document.get("configured_items")),
        "processed_items": _safe_int(document.get("processed_items")),
        "collected": _safe_int(document.get("collected") or document.get("messages_collected")),
        "indexed": _safe_int(document.get("indexed") or document.get("saved")),
        "duplicates_skipped": _safe_int(document.get("duplicates_skipped")),
        "skipped_existing": _safe_int(document.get("skipped_existing") or details.get("skipped_existing")),
        "skipped_noise": _safe_int(document.get("skipped_noise") or details.get("skipped_noise")),
        "skipped_informational": _safe_int(document.get("skipped_informational")),
        "total_seen": _collection_run_total_seen(document, details),
        "last_cursor": str(
            document.get("last_cursor")
            or details.get("last_cursor")
            or details.get("latest_published_at")
            or details.get("last_seen_message_id")
            or ""
        ),
        "rate_limit_detected": bool(document.get("rate_limit_detected") or details.get("rate_limit_detected") or details.get("rate_limited")),
        "stopped_reason": str(document.get("stopped_reason") or details.get("stopped_reason") or ""),
        "local_export_enabled": bool(local_export.get("enabled", False)),
        "local_export_received": _safe_int(local_export.get("received")),
        "local_export_appended": _safe_int(local_export.get("appended")),
        "local_export_skipped_existing": _safe_int(local_export.get("skipped_existing")),
        "local_export_file": str(local_export.get("file_path") or ""),
        "local_export": local_export,
        "errors": _safe_int(document.get("errors")),
        "message": str(document.get("message") or ""),
        "details": details,
    }


def ensure_collection_state_index() -> None:
    client = get_elastic_client()
    properties = {
        "source": {"type": "keyword"},
        "key": {"type": "keyword"},
        "first_run_completed": {"type": "boolean"},
        "last_successful_run_at": {"type": "date"},
        "last_started_at": {"type": "date"},
        "last_finished_at": {"type": "date"},
        "last_cursor": {"type": "keyword", "ignore_above": 2048},
        "latest_published_at": {"type": "date"},
        "last_message_id": {"type": "long"},
        "last_message_date": {"type": "date"},
        "total_items_seen": {"type": "long"},
        "total_items_processed": {"type": "long"},
        "total_items_indexed": {"type": "long"},
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

    _safe_create_index(client, COLLECTION_STATE_INDEX, mappings={"properties": properties})


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
        for field in (
            "first_run_completed",
            "last_successful_run_at",
            "last_started_at",
            "last_finished_at",
            "last_cursor",
            "latest_published_at",
            "last_message_id",
            "last_message_date",
            "total_items_seen",
            "total_items_processed",
            "total_items_indexed",
        ):
            value = document["state"].get(field)
            if value is not None and value != "":
                document[field] = value
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
        return {
            "items": [],
            "detections": [],
            "total": 0,
            "limit": normalized_limit,
            "offset": normalized_offset,
            "has_more": False,
            "source": source,
        }

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
            track_total_hits=True,
            sort=[{sort_field: {"order": "desc", "unmapped_type": "date", "missing": "_last"}}],
        )
    except ElasticsearchQueryError:
        return {
            "items": [],
            "detections": [],
            "total": 0,
            "limit": normalized_limit,
            "offset": normalized_offset,
            "has_more": False,
            "source": source,
        }

    hits = response.get("hits") if isinstance(response.get("hits"), dict) else {}
    hit_list = hits.get("hits") if isinstance(hits.get("hits"), list) else []
    detections = [
        normalize_detection_document(hit) for hit in hit_list if isinstance(hit, dict)
    ]
    total = search_total(hits)
    return {
        "items": detections,
        "detections": detections,
        "total": total,
        "limit": normalized_limit,
        "offset": normalized_offset,
        "has_more": normalized_offset + len(detections) < total,
        "source": source,
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
    scan_mode = str(result.get("scan_mode") or result.get("effective_mode") or "")
    requested_scan_mode = str(result.get("requested_scan_mode") or result.get("mode_requested") or scan_mode)
    scan_group_id = str(result.get("scan_group_id") or run_id)
    local_export = result.get("local_export") if isinstance(result.get("local_export"), dict) else {}
    document = {
        "run_id": run_id,
        "scan_group_id": scan_group_id,
        "source": source,
        "mode_requested": requested_scan_mode,
        "effective_mode": str(result.get("effective_mode") or scan_mode or requested_scan_mode),
        "requested_scan_mode": requested_scan_mode,
        "scan_mode": scan_mode,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": duration_seconds,
        "status": status,
        "configured_items": int(result.get("configured_items") or 0),
        "processed_items": int(result.get("processed_items") or 0),
        "collected": collected,
        "indexed": indexed,
        "duplicates_skipped": duplicates,
        "skipped_existing": int(result.get("skipped_existing") or 0),
        "skipped_noise": int(result.get("skipped_noise") or 0),
        "skipped_informational": int(result.get("skipped_informational") or 0),
        "total_seen": int(result.get("total_seen") or collected),
        "last_cursor": str(result.get("last_cursor") or ""),
        "rate_limit_detected": bool(result.get("rate_limit_detected") or False),
        "stopped_reason": str(result.get("stopped_reason") or ""),
        "local_export": local_export,
        "errors": errors,
        "message": _scan_run_message(result),
        "details": result.get("details") if isinstance(result.get("details"), dict) else {},
    }
    document = _normalize_collection_run_document(document)
    try:
        response = client.index(index=COLLECTION_RUNS_INDEX, id=run_id, document=document, refresh=True)
    except BadRequestError as exc:
        logger.warning(
            "Unable to persist collection run summary for %s: BadRequestError body=%s",
            source,
            _elasticsearch_error_body(exc),
        )
        return {"index": COLLECTION_RUNS_INDEX, "id": run_id, "result": "failed"}
    except Exception as exc:
        logger.warning("Unable to persist collection run summary for %s: %s", source, _elasticsearch_error_body(exc))
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


def _collection_run_from_hit(hit: dict[str, Any]) -> dict[str, Any]:
    doc = hit.get("_source") if isinstance(hit.get("_source"), dict) else hit
    if not isinstance(doc, dict):
        return {}
    return {"id": hit.get("_id"), **doc}


def _latest_single_scan_run(client: Elasticsearch) -> tuple[str | None, list[dict[str, Any]]]:
    if not client.indices.exists(index=COLLECTION_RUNS_INDEX):
        return None, []
    try:
        response = client.search(
            index=COLLECTION_RUNS_INDEX,
            query={"terms": {"source": list(LATEST_SCAN_SOURCES)}},
            size=1,
            sort=[{"ended_at": {"order": "desc", "unmapped_type": "date", "missing": "_last"}}],
        )
    except Exception as exc:
        logger.warning("Unable to read latest single scan run: %s", exc.__class__.__name__)
        return None, []
    hits = response.get("hits", {}).get("hits", [])
    if not isinstance(hits, list) or not hits:
        return None, []
    run = _collection_run_from_hit(hits[0])
    return str(run.get("scan_group_id") or "") or None, [run]


def _latest_scan_run_group(client: Elasticsearch, *, scope: str = "latest_group") -> tuple[str | None, list[dict[str, Any]]]:
    if scope == "latest_source":
        return _latest_single_scan_run(client)

    if not client.indices.exists(index=COLLECTION_RUNS_INDEX):
        return None, []
    try:
        response = client.search(
            index=COLLECTION_RUNS_INDEX,
            query={"terms": {"source": list(LATEST_SCAN_SOURCES)}},
            size=1,
            sort=[{"ended_at": {"order": "desc", "unmapped_type": "date", "missing": "_last"}}],
        )
    except Exception as exc:
        logger.warning("Unable to read latest scan run group: %s", exc.__class__.__name__)
        return None, []

    hits = response.get("hits", {}).get("hits", [])
    if not isinstance(hits, list) or not hits:
        return None, []

    anchor = _collection_run_from_hit(hits[0])
    scan_group_id = str(anchor.get("scan_group_id") or "")
    if not scan_group_id:
        return None, [anchor]

    try:
        grouped = client.search(
            index=COLLECTION_RUNS_INDEX,
            query={
                "bool": {
                    "filter": [
                        {"terms": {"source": list(LATEST_SCAN_SOURCES)}},
                        {"term": {"scan_group_id": scan_group_id}},
                    ]
                }
            },
            size=len(LATEST_SCAN_SOURCES),
            sort=[{"ended_at": {"order": "desc", "unmapped_type": "date", "missing": "_last"}}],
        )
    except Exception as exc:
        logger.warning("Unable to read collection runs for scan_group_id=%s: %s", scan_group_id, exc.__class__.__name__)
        return scan_group_id, [anchor]

    grouped_hits = grouped.get("hits", {}).get("hits", [])
    runs = [_collection_run_from_hit(hit) for hit in grouped_hits if isinstance(hit, dict)] if isinstance(grouped_hits, list) else []
    runs = [run for run in runs if run]
    if not runs:
        runs = [anchor]
    return scan_group_id, runs


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _source_scan_metrics(run: dict[str, Any], severity_counts: dict[str, int] | None = None) -> dict[str, Any]:
    details = run.get("details") if isinstance(run.get("details"), dict) else {}
    source = str(run.get("source") or "")
    skipped_existing = _safe_int(run.get("skipped_existing") or details.get("skipped_existing"))
    duplicates = _safe_int(run.get("duplicates_skipped")) + skipped_existing
    indexed = _safe_int(run.get("indexed"))
    collected = _safe_int(run.get("collected") or run.get("messages_collected"))
    total_seen = _safe_int(run.get("total_seen") or details.get("results_seen"))
    if total_seen <= 0:
        if source == "telegram":
            total_seen = _safe_int(details.get("messages_collected")) + _safe_int(details.get("messages_already_known")) + skipped_existing
        elif source == "google_alerts":
            total_seen = _safe_int(details.get("rss_entries_collected")) + skipped_existing
        else:
            total_seen = collected + skipped_existing

    if source == "google_alerts":
        new_items = _safe_int(details.get("new_feed_entries") or collected)
    elif source == "telegram":
        new_items = _safe_int(details.get("new_messages_found") or collected)
    else:
        new_items = collected

    status = str(run.get("status") or "unknown")
    if status == "error":
        status = "failed"
    mode = str(run.get("effective_mode") or run.get("scan_mode") or details.get("scan_mode") or "unknown")
    requested_mode = str(run.get("mode_requested") or run.get("requested_scan_mode") or mode)
    local_export = run.get("local_export") if isinstance(run.get("local_export"), dict) else {}
    if not local_export:
        local_export = details.get("local_export") if isinstance(details.get("local_export"), dict) else {}
    if not local_export and run.get("local_export_file"):
        local_export = {
            "enabled": bool(run.get("local_export_enabled")),
            "file_path": run.get("local_export_file"),
            "received": _safe_int(run.get("local_export_received")),
            "appended": _safe_int(run.get("local_export_appended")),
            "skipped_existing": _safe_int(run.get("local_export_skipped_existing")),
        }
    source_counts = severity_counts or {}
    payload: dict[str, Any] = {
        "status": status,
        "run_id": run.get("run_id"),
        "scan_group_id": run.get("scan_group_id"),
        "mode_requested": requested_mode,
        "effective_mode": mode,
        "limit": _safe_int(details.get("max_items_per_run")),
        "items_seen": total_seen,
        "new_items": new_items,
        "indexed": indexed,
        "duplicates": duplicates,
        "duplicates_skipped": duplicates,
        "errors": _safe_int(run.get("errors")),
        "high_severity": _safe_int(source_counts.get("high")),
        "medium_severity": _safe_int(source_counts.get("medium")),
        "low_severity": _safe_int(source_counts.get("low")),
        "started_at": run.get("started_at"),
        "finished_at": run.get("ended_at"),
        "duration_seconds": run.get("duration_seconds"),
        "message": run.get("message") or "",
        "cursor_before": details.get("cursor_before") or details.get("query_window_start") or "",
        "cursor_after": details.get("last_cursor") or run.get("last_cursor") or "",
        "local_export": local_export,
        "details": details,
    }

    if source == "github":
        payload.update(
            {
                "queries_processed": _safe_int(details.get("queries_processed")),
                "files_fetched": _safe_int(details.get("files_fetched")),
                "results_seen": _safe_int(details.get("results_seen") or total_seen),
            }
        )
    elif source == "google_alerts":
        payload.update(
            {
                "feeds_scanned": _safe_int(details.get("feeds_processed") or run.get("feeds_processed")),
                "entries_seen": total_seen,
                "new_entries": new_items,
                "latest_published_at": details.get("latest_published_at") or run.get("last_cursor") or "",
            }
        )
    elif source == "telegram":
        payload.update(
            {
                "channels_watched": _safe_int(details.get("channels_loaded") or run.get("channels_loaded")),
                "channels_with_new_messages": _safe_int(details.get("tracked_channels")),
                "messages_seen": total_seen,
                "new_messages": new_items,
                "last_message_id": details.get("last_seen_message_id") or run.get("last_cursor") or "",
                "last_message_date": details.get("last_message_date") or "",
            }
        )
    return payload


def _scan_group_detection_query(
    runs: list[dict[str, Any]],
    scan_group_id: str | None,
    *,
    source: str | None = None,
    severity: str | None = None,
) -> dict[str, Any]:
    filters: list[dict[str, Any]] = []
    if scan_group_id:
        filters.append({"term": {"scan_group_id": scan_group_id}})
    else:
        sources = [str(run.get("source")) for run in runs if run.get("source")]
        if sources:
            filters.append({"terms": {"source": sources}})
        started = [_parse_datetime(run.get("started_at")) for run in runs]
        finished = [_parse_datetime(run.get("ended_at")) for run in runs]
        started = [value for value in started if value is not None]
        finished = [value for value in finished if value is not None]
        if started and finished:
            filters.append(
                {
                    "range": {
                        "processed_at": {
                            "gte": min(started).isoformat(),
                            "lte": max(finished).isoformat(),
                        }
                    }
                }
            )
    if source:
        filters.append({"term": {"source": source}})
    if severity:
        filters.append({"term": {"severity": severity}})
    return {"bool": {"filter": filters}} if filters else {"match_none": {}}


def _latest_scan_detections_page(
    client: Elasticsearch,
    runs: list[dict[str, Any]],
    scan_group_id: str | None,
    *,
    source: str | None = None,
    severity: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    normalized_limit = _normalize_limit(limit)
    normalized_offset = max(0, offset)
    if not client.indices.exists(index=INDEX_NAME):
        return {
            "items": [],
            "detections": [],
            "total": 0,
            "limit": normalized_limit,
            "offset": normalized_offset,
            "has_more": False,
            "source": source,
            "run_id": scan_group_id,
        }

    properties = _index_properties(client)
    sort_field = resolve_timeline_date_field(properties) or "processed_at"
    query = _scan_group_detection_query(runs, scan_group_id, source=source, severity=severity)
    try:
        response = _execute_search(
            client,
            operation="latest_scan_detections",
            query=query,
            from_=normalized_offset,
            size=normalized_limit,
            track_total_hits=True,
            sort=[{sort_field: {"order": "desc", "unmapped_type": "date", "missing": "_last"}}],
        )
    except ElasticsearchQueryError:
        return {
            "items": [],
            "detections": [],
            "total": 0,
            "limit": normalized_limit,
            "offset": normalized_offset,
            "has_more": False,
            "source": source,
            "run_id": scan_group_id,
        }

    hits = response.get("hits") if isinstance(response.get("hits"), dict) else {}
    hit_list = hits.get("hits") if isinstance(hits.get("hits"), list) else []
    detections = [normalize_detection_document(hit) for hit in hit_list if isinstance(hit, dict)]
    total = search_total(hits)
    return {
        "items": detections,
        "detections": detections,
        "total": total,
        "limit": normalized_limit,
        "offset": normalized_offset,
        "has_more": normalized_offset + len(detections) < total,
        "source": source,
        "severity": severity,
        "run_id": scan_group_id,
    }


def _severity_counts_for_latest_scan(
    client: Elasticsearch,
    runs: list[dict[str, Any]],
    scan_group_id: str | None,
    *,
    source: str | None = None,
) -> dict[str, int]:
    if not client.indices.exists(index=INDEX_NAME):
        return {}
    try:
        response = _execute_search(
            client,
            operation="latest_scan_severity_counts",
            query=_scan_group_detection_query(runs, scan_group_id, source=source),
            size=0,
            aggs={"by_severity": {"terms": {"field": "severity", "size": 20}}},
        )
    except ElasticsearchQueryError:
        return {}
    aggregations = response.get("aggregations") if isinstance(response.get("aggregations"), dict) else {}
    return terms_aggregation_dict(aggregations.get("by_severity"))


def _scan_group_status(runs: list[dict[str, Any]]) -> str:
    statuses = {str(run.get("status") or "unknown").lower() for run in runs}
    if not runs:
        return "not_found"
    if "error" in statuses or "failed" in statuses:
        return "failed" if len(runs) == 1 else "partial"
    if "warning" in statuses or "partial" in statuses:
        return "partial"
    if statuses == {"success"}:
        return "success"
    return "partial" if len(statuses) > 1 else next(iter(statuses))


def get_latest_scan_report(*, scope: str = "latest_group") -> dict[str, Any]:
    client = get_elastic_client()
    normalized_scope = scope if scope in {"latest_group", "latest_source"} else "latest_group"
    scan_group_id, runs = _latest_scan_run_group(client, scope=normalized_scope)
    sources_present = sorted({str(run.get("source") or "") for run in runs if run.get("source")})
    source_count = len(sources_present)
    if normalized_scope == "latest_source":
        scan_scope = "single_source"
    elif source_count <= 1:
        scan_scope = "single_source"
    else:
        scan_scope = "latest_group"
    missing_sources = [source for source in LATEST_SCAN_SOURCES if source not in sources_present]

    if not runs:
        return {
            "scan_group_id": None,
            "scan_scope": scan_scope,
            "source_count": 0,
            "sources_included": [],
            "missing_sources": list(LATEST_SCAN_SOURCES),
            "run": None,
            "summary": {
                "total_items_seen": 0,
                "total_new_items": 0,
                "total_indexed": 0,
                "total_duplicates": 0,
                "total_errors": 0,
                "high_severity": 0,
                "medium_severity": 0,
                "low_severity": 0,
            },
            "sources": {},
            "latest_detections": [],
        }

    started_values = [_parse_datetime(run.get("started_at")) for run in runs]
    finished_values = [_parse_datetime(run.get("ended_at")) for run in runs]
    started_values = [value for value in started_values if value is not None]
    finished_values = [value for value in finished_values if value is not None]
    started_at = min(started_values).isoformat() if started_values else ""
    finished_at = max(finished_values).isoformat() if finished_values else ""
    duration_seconds = max(
        0.0,
        ((max(finished_values) - min(started_values)).total_seconds() if started_values and finished_values else 0.0),
    )
    mode_requested_values = {str(run.get("mode_requested") or run.get("requested_scan_mode") or "") for run in runs}
    effective_mode_values = {str(run.get("effective_mode") or run.get("scan_mode") or "") for run in runs}
    mode_requested_values.discard("")
    effective_mode_values.discard("")

    source_metrics: dict[str, Any] = {}
    for run in sorted(runs, key=lambda item: str(item.get("source") or "")):
        source = str(run.get("source") or "")
        if source not in LATEST_SCAN_SOURCES:
            continue
        counts = _severity_counts_for_latest_scan(client, runs, scan_group_id, source=source)
        source_metrics[source] = _source_scan_metrics(run, counts)

    severity_counts = _severity_counts_for_latest_scan(client, runs, scan_group_id)
    latest = _latest_scan_detections_page(client, runs, scan_group_id, limit=10, offset=0)
    summary = {
        "total_items_seen": sum(_safe_int(item.get("items_seen")) for item in source_metrics.values()),
        "total_new_items": sum(_safe_int(item.get("new_items")) for item in source_metrics.values()),
        "total_indexed": sum(_safe_int(item.get("indexed")) for item in source_metrics.values()),
        "total_duplicates": sum(_safe_int(item.get("duplicates")) for item in source_metrics.values()),
        "total_errors": sum(_safe_int(item.get("errors")) for item in source_metrics.values()),
        "high_severity": _safe_int(severity_counts.get("high")),
        "medium_severity": _safe_int(severity_counts.get("medium")),
        "low_severity": _safe_int(severity_counts.get("low")),
    }
    return {
        "scan_group_id": scan_group_id,
        "scan_scope": scan_scope,
        "source_count": source_count,
        "sources_included": sources_present,
        "missing_sources": missing_sources,
        "run": {
            "run_id": scan_group_id,
            "status": _scan_group_status(runs),
            "mode_requested": next(iter(mode_requested_values), "unknown") if len(mode_requested_values) <= 1 else "mixed",
            "effective_mode": next(iter(effective_mode_values), "unknown") if len(effective_mode_values) <= 1 else "mixed",
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": duration_seconds,
            "sources": sources_present,
        },
        "summary": summary,
        "sources": source_metrics,
        "latest_detections": latest.get("items", []),
    }


def list_latest_scan_detections(
    *,
    source: str | None = None,
    severity: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    client = get_elastic_client()
    scan_group_id, runs = _latest_scan_run_group(client)
    if not runs:
        normalized_limit = _normalize_limit(limit)
        normalized_offset = max(0, offset)
        return {
            "items": [],
            "detections": [],
            "total": 0,
            "limit": normalized_limit,
            "offset": normalized_offset,
            "has_more": False,
            "source": source,
            "severity": severity,
            "run_id": None,
        }
    return _latest_scan_detections_page(
        client,
        runs,
        scan_group_id,
        source=source,
        severity=severity,
        limit=limit,
        offset=offset,
    )


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
