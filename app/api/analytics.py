from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.elasticsearch_errors import run_elasticsearch_endpoint
from app.analytics_intelligence import (
    get_correlations,
    get_intelligence_summary,
    get_source_diagnostics,
)
from app.collectors.google_alerts_collector import inspect_google_alerts_config
from app.collectors.telegram_collector import load_telegram_sources
from app.config import settings
from app.schemas.analytics import (
    ALLOWED_TIMELINE_INTERVALS,
    AnalyticsSummaryResponse,
    AnalyticsTimelineResponse,
    DEFAULT_TIMELINE_DAYS,
    MAX_TIMELINE_DAYS,
)
from app.storage.elastic_client import (
    ElasticsearchUnavailableError,
    MAX_DETECTION_LIST_LIMIT,
    get_analytics_charts,
    get_analytics_summary,
    get_analytics_timeline,
    get_latest_scan_report,
    get_source_health,
    list_collection_runs,
    list_latest_scan_detections,
)
from app.storage.local_data_exporter import local_data_export_status
from app.storage.scan_status import get_all_scan_statuses


router = APIRouter(tags=["analytics"])


@router.get("/analytics/summary", response_model=AnalyticsSummaryResponse)
def analytics_summary() -> AnalyticsSummaryResponse:
    result = run_elasticsearch_endpoint(get_analytics_summary, endpoint="/analytics/summary")
    return AnalyticsSummaryResponse(**result)


@router.get("/analytics/timeline", response_model=AnalyticsTimelineResponse)
def analytics_timeline(
    interval: str = Query(default="day"),
    days: int = Query(default=DEFAULT_TIMELINE_DAYS, ge=1, le=MAX_TIMELINE_DAYS),
) -> AnalyticsTimelineResponse:
    if interval not in ALLOWED_TIMELINE_INTERVALS:
        allowed = ", ".join(sorted(ALLOWED_TIMELINE_INTERVALS))
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": f"Invalid interval '{interval}'. Allowed values: {allowed}",
                "error_type": "ValidationError",
                "endpoint": "/analytics/timeline",
            },
        )

    result = run_elasticsearch_endpoint(
        lambda: get_analytics_timeline(interval=interval, days=days),  # type: ignore[arg-type]
        endpoint="/analytics/timeline",
    )
    return AnalyticsTimelineResponse(**result)


def _source_enabled(source: str) -> bool:
    if source == "github":
        return bool(settings.GITHUB_TOKEN)
    if source == "google_alerts":
        config = inspect_google_alerts_config()
        return bool(config.get("valid_feeds_count", 0))
    if source == "telegram":
        return bool(settings.TELEGRAM_API_ID and settings.TELEGRAM_API_HASH and load_telegram_sources())
    return False


def _source_health_entry(source: str, display_name: str) -> dict[str, object]:
    enabled = _source_enabled(source)
    status_payload = get_all_scan_statuses([source]).get(source)
    if status_payload:
        errors = int(status_payload.get("errors") or 0)
        indexed = status_payload.get("indexed_last_scan", status_payload.get("last_indexed", 0))
        duplicates = status_payload.get("duplicates_skipped", status_payload.get("last_duplicates", 0))
        state = str(status_payload.get("state") or "unknown")
        if not enabled:
            scan_result = "skipped"
            status = "disabled"
        else:
            scan_result = "failed" if state == "failed" else "partial" if errors else "completed" if state == "completed" else state
            status = "error" if state == "failed" else "warning" if errors else "healthy" if state == "completed" else "warning"
        message = str(status_payload.get("last_message") or status_payload.get("last_scan_result") or scan_result)
        if status == "disabled":
            message = "source disabled"
        if status == "healthy" and int(indexed or 0) == 0:
            message = f"{display_name} scan completed successfully. No new validated detections were indexed."
        return {
            "source": source,
            "name": display_name,
            "enabled": enabled,
            "scan_result": scan_result,
            "last_scan_at": status_payload.get("last_scan_time") or "unknown",
            "last_scan_time": status_payload.get("last_scan_time") or "unknown",
            "last_scan_status": status_payload.get("last_scan_status") or status_payload.get("last_scan_result") or "unknown",
            "last_scan_result": scan_result,
            "message": message,
            "last_message": message,
            "indexed_count": indexed,
            "duplicate_count": duplicates,
            "error_count": errors,
            "warning_count": errors,
            "last_error": str(status_payload.get("error") or "") if errors else "",
            "last_indexed": indexed,
            "last_duplicates": duplicates,
            "last_errors": errors,
            "indexed_last_scan": indexed,
            "duplicates_skipped": duplicates,
            "errors": errors,
            "warnings": errors,
            "status": status,
            "state": status_payload.get("state") or "unknown",
            "task_id": status_payload.get("task_id") or "",
            "started_at": status_payload.get("started_at") or "",
            "ended_at": status_payload.get("ended_at") or "",
        }

    if not enabled:
        status = "disabled"
        result = "skipped"
        message = "source disabled"
    else:
        status = "unknown"
        result = "unknown"
        message = "unknown"

    return {
        "source": source,
        "name": display_name,
        "enabled": enabled,
        "scan_result": result,
        "last_scan_at": "unknown",
        "last_scan_time": "unknown",
        "last_scan_status": "unknown",
        "last_scan_result": result,
        "message": message,
        "last_message": message,
        "indexed_count": 0,
        "duplicate_count": 0,
        "error_count": 0,
        "warning_count": 0,
        "last_error": "",
        "last_indexed": 0,
        "last_duplicates": 0,
        "last_errors": 0,
        "indexed_last_scan": "unknown",
        "duplicates_skipped": "unknown",
        "errors": "unknown",
        "warnings": 0,
        "status": status,
        "note": "No persisted scan status is available yet. Run a collection to populate this source.",
    }


@router.get("/analytics/source-health")
def analytics_source_health() -> dict[str, object]:
    sources = [
        ("github", "GitHub"),
        ("google_alerts", "Google Alerts"),
        ("telegram", "Telegram"),
    ]
    source_metadata = [(source, display_name, _source_enabled(source)) for source, display_name in sources]
    try:
        return get_source_health(source_metadata)
    except ElasticsearchUnavailableError:
        result = [_source_health_entry(source, display_name) for source, display_name in sources]
        return {"sources": result}
    except Exception:
        result = [
            {
                "source": source,
                "name": display_name,
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
            for source, display_name, enabled in source_metadata
        ]
        return {"sources": result}


@router.get("/analytics/collection-runs")
def analytics_collection_runs(
    source: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
) -> dict[str, object]:
    return run_elasticsearch_endpoint(
        lambda: list_collection_runs(source=source, status=status, limit=limit),
        endpoint="/analytics/collection-runs",
    )


@router.get("/analytics/local-data-export")
def analytics_local_data_export() -> dict[str, object]:
    return local_data_export_status()


@router.get("/analytics/latest-scan")
def analytics_latest_scan(
    scope: str = Query(default="latest_group", pattern="^(latest_group|latest_source)$"),
) -> dict[str, object]:
    return run_elasticsearch_endpoint(
        lambda: get_latest_scan_report(scope=scope),
        endpoint="/analytics/latest-scan",
    )


@router.get("/analytics/latest-scan/detections")
def analytics_latest_scan_detections(
    source: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=MAX_DETECTION_LIST_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    allowed_sources = {"github", "google_alerts", "telegram"}
    if source and source not in allowed_sources:
        raise HTTPException(status_code=400, detail=f"Invalid source: {source}")
    return run_elasticsearch_endpoint(
        lambda: list_latest_scan_detections(
            source=source,
            severity=severity,
            limit=limit,
            offset=offset,
        ),
        endpoint="/analytics/latest-scan/detections",
    )


@router.get("/analytics/charts")
def analytics_charts(
    source: str | None = Query(default=None),
    signal_type: str | None = Query(default=None),
    organization: str | None = Query(default=None),
    category: str | None = Query(default=None),
    country: str | None = Query(default=None),
    risk_category: str | None = Query(default=None),
    confidence: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    date_range: str | None = Query(default=None),
) -> dict[str, object]:
    result = run_elasticsearch_endpoint(
        lambda: get_analytics_charts(
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
        ),
        endpoint="/analytics/charts",
    )
    return result


@router.get("/analytics/correlations")
def analytics_correlations(
    limit: int = Query(default=500, ge=10, le=1000),
) -> dict[str, object]:
    return run_elasticsearch_endpoint(
        lambda: get_correlations(limit=limit),
        endpoint="/analytics/correlations",
    )


@router.get("/analytics/intelligence-summary")
def analytics_intelligence_summary(
    limit: int = Query(default=500, ge=10, le=1000),
) -> dict[str, object]:
    return run_elasticsearch_endpoint(
        lambda: get_intelligence_summary(limit=limit),
        endpoint="/analytics/intelligence-summary",
    )


@router.get("/analytics/source-diagnostics")
def analytics_source_diagnostics() -> dict[str, object]:
    return run_elasticsearch_endpoint(
        get_source_diagnostics,
        endpoint="/analytics/source-diagnostics",
    )
