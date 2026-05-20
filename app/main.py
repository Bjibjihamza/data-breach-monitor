from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.analytics import router as analytics_router
from app.api.dashboard import router as dashboard_router
from app.api.detections import router as detections_router
from app.collectors.google_alerts_collector import inspect_google_alerts_config
from app.collectors.scan_modes import (
    COLLECTOR_STATE_KEY,
    DEFAULT_SCAN_MODE,
    SCAN_MODE_BACKFILL,
    SCAN_MODE_INCREMENTAL,
    normalize_scan_mode,
)
from app.collectors.telegram_collector import inspect_telegram_config
from app.config import settings
from app.startup.initial_backfill import (
    initial_backfill_status,
    run_initial_backfill_blocking,
    schedule_initial_backfill_async,
)
from app.storage.elastic_client import (
    ElasticsearchUnavailableError,
    delete_mock_paste_detections,
    list_collection_states,
)
from app.storage.scan_status import (
    SUPPORTED_SOURCES,
    get_aggregate_scan_status,
    get_source_live_status,
    init_scan_run,
    is_source_active,
)
from app.tasks import (
    run_google_alerts_scan,
    run_mock_paste_scan,
    scan_github_task,
    scan_telegram_channels,
)
from app.watchlists.loader import (
    github_search_specs,
    load_global_risks,
    load_organizations,
    organization_watchlists_enabled,
)


logger = logging.getLogger(__name__)


app = FastAPI(
    title="External Data Exposure & Breach Monitor",
    description=(
        "Defensive OSINT platform for publicly exposed sensitive data across "
        "authorized public sources. Not a vulnerability scanner."
    ),
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(detections_router)
app.include_router(analytics_router)
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
app.mount(
    "/dashboard/assets",
    StaticFiles(directory=_FRONTEND_DIST / "assets", check_dir=False),
    name="dashboard-assets",
)
app.include_router(dashboard_router)


@app.on_event("startup")
def _on_startup() -> None:
    """Trigger the one-time initial backfill in the background.

    The orchestration waits for Elasticsearch internally; this hook only
    schedules it, so the API never blocks on collector latency.
    """

    schedule_initial_backfill_async()


def _resolve_scan_mode(mode: str | None) -> str:
    """Return a validated scan mode string for API endpoints."""

    if mode is None:
        return DEFAULT_SCAN_MODE
    candidate = str(mode).strip().lower()
    if candidate not in {SCAN_MODE_BACKFILL, SCAN_MODE_INCREMENTAL}:
        raise HTTPException(status_code=400, detail=f"invalid scan mode: {mode!r}")
    return normalize_scan_mode(candidate)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "external-data-exposure-breach-monitor",
        "status": "running",
        "purpose": "external data exposure and breach monitoring",
    }


@app.get("/health")
def health() -> dict[str, bool | str]:
    return {"success": True, "status": "healthy"}


@app.get("/debug/google-alerts-config")
def debug_google_alerts_config() -> dict[str, object]:
    return inspect_google_alerts_config()


@app.get("/debug/github-config")
def debug_github_config() -> dict[str, object]:
    specs = github_search_specs()
    organizations = load_organizations()
    global_risks = load_global_risks()
    organization_profiles_enabled = organization_watchlists_enabled()
    return {
        "total_query_specs": len(specs),
        "max_queries_per_run": settings.GITHUB_MAX_QUERIES_PER_RUN,
        "max_file_fetches": settings.GITHUB_MAX_FILE_FETCHES_PER_RUN,
        "max_pages_per_query": settings.GITHUB_MAX_PAGES_PER_QUERY,
        "max_results_per_query": settings.GITHUB_MAX_RESULTS_PER_QUERY,
        "incremental_max_items": settings.GITHUB_INCREMENTAL_MAX_ITEMS,
        "initial_backfill_max_items": settings.INITIAL_BACKFILL_MAX_ITEMS_PER_SOURCE,
        "first_5_queries": [spec.query for spec in specs[:5]],
        "global_policy": {
            "global_first": True,
            "global_risk_categories": len(global_risks),
            "global_risk_queries": sum(len(category.queries) for category in global_risks),
            "global_risks_path": str(settings.WATCHLISTS_GLOBAL_RISKS_PATH),
        },
        "organization_watchlists": {
            "enabled": organization_profiles_enabled,
            "profiles_loaded": len(organizations),
            "profile_names": [profile.name for profile in organizations[:20]],
            "organizations_file": str(settings.WATCHLISTS_ORGANIZATIONS_FILE),
            "organizations_dir": str(settings.WATCHLISTS_ORGANIZATIONS_DIR),
        },
        "github_token_present": bool(settings.GITHUB_TOKEN),
    }


@app.get("/debug/telegram-config")
def debug_telegram_config() -> dict[str, object]:
    return inspect_telegram_config()


@app.get("/debug/collection-state")
def debug_collection_state() -> dict[str, object]:
    try:
        return list_collection_states(limit=200)
    except ElasticsearchUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/collector-state")
def collector_state() -> dict[str, object]:
    try:
        result = list_collection_states(limit=500)
    except ElasticsearchUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    grouped: dict[str, dict[str, object]] = {
        source: {"collector": {}, "states": []}
        for source in ("github", "google_alerts", "telegram")
    }
    for state in result.get("states", []):
        if not isinstance(state, dict):
            continue
        source = str(state.get("source") or "")
        if source not in grouped:
            continue
        if state.get("key") == COLLECTOR_STATE_KEY:
            grouped[source]["collector"] = state
        else:
            grouped[source]["states"].append(state)
    return {
        "index": "collection_state",
        "total": result.get("total", 0),
        "sources": grouped,
    }


@app.get("/admin/initial-backfill")
def admin_initial_backfill_status() -> dict[str, object]:
    return initial_backfill_status()


@app.post("/admin/initial-backfill/run")
def admin_initial_backfill_run() -> dict[str, object]:
    if settings.APP_ENV != "development":
        raise HTTPException(status_code=403, detail="Development-only endpoint")
    schedule_initial_backfill_async()
    return {"success": True, "scheduled": True}


@app.post("/admin/initial-backfill/run-now")
def admin_initial_backfill_run_now() -> dict[str, object]:
    if settings.APP_ENV != "development":
        raise HTTPException(status_code=403, detail="Development-only endpoint")
    summary = run_initial_backfill_blocking()
    return {"success": True, "results": summary}


@app.post("/scan/mock")
def scan_mock() -> dict[str, bool | str]:
    task = run_mock_paste_scan.delay()
    mark_scan_queued("mock_paste", task_id=task.id)
    return {"success": True, "message": "Task queued", "task": task.id}


def _queue_source_scan(
    source: str,
    task,
    mode: str | None,
    *,
    scan_group_id: str | None = None,
    raise_on_conflict: bool = True,
) -> dict[str, object]:
    if source not in SUPPORTED_SOURCES:
        raise HTTPException(status_code=400, detail=f"unsupported source: {source}")

    if is_source_active(source):
        active = get_source_live_status(source)
        conflict = {
            "success": False,
            "source": source,
            "status": "already_running",
            "active_task_id": active.get("task_id"),
            "run_id": active.get("run_id"),
            "scan_group_id": active.get("scan_group_id"),
            "message": f"{source.replace('_', ' ').title()} scan is already running",
        }
        if raise_on_conflict:
            raise HTTPException(status_code=409, detail=conflict)
        return conflict

    scan_mode = _resolve_scan_mode(mode)
    source_group_id = scan_group_id or f"scan-{uuid4().hex}"
    run_id = f"{source}-{uuid4().hex}"
    async_result = task.delay(mode=scan_mode, scan_group_id=source_group_id, run_id=run_id)
    init_scan_run(
        source,
        task_id=async_result.id,
        run_id=run_id,
        scan_group_id=source_group_id,
        requested_mode=scan_mode,
        effective_mode=scan_mode,
    )
    live = get_source_live_status(source)
    return {
        "success": True,
        "source": source,
        "status": "queued",
        "scan_mode": scan_mode,
        "requested_mode": scan_mode,
        "effective_mode": live.get("effective_mode") or scan_mode,
        "scan_group_id": source_group_id,
        "run_id": run_id,
        "task_id": async_result.id,
        "task": async_result.id,
    }


@app.get("/scan/status")
def scan_status_all() -> dict[str, object]:
    return get_aggregate_scan_status()


@app.get("/scan/status/{source}")
def scan_status_source(source: str) -> dict[str, object]:
    normalized = source.strip().lower().replace("-", "_")
    if normalized not in SUPPORTED_SOURCES:
        raise HTTPException(status_code=404, detail=f"unknown source: {source}")
    return get_source_live_status(normalized)


@app.post("/scan/google-alerts")
def scan_google_alerts(mode: str | None = Query(default=None)) -> dict[str, object]:
    return _queue_source_scan("google_alerts", run_google_alerts_scan, mode)


@app.post("/scan/telegram")
def scan_telegram(mode: str | None = Query(default=None)) -> dict[str, object]:
    return _queue_source_scan("telegram", scan_telegram_channels, mode)


@app.post("/scan/github")
def scan_github(mode: str | None = Query(default=None)) -> dict[str, object]:
    return _queue_source_scan("github", scan_github_task, mode)


@app.post("/scan/all")
def scan_all(mode: str | None = Query(default=None)) -> dict[str, object]:
    """Enqueue all three external sources at once. Defaults to incremental."""

    scan_mode = _resolve_scan_mode(mode)
    scan_group_id = f"scan-all-{uuid4().hex}"
    results = {
        "github": _queue_source_scan(
            "github",
            scan_github_task,
            scan_mode,
            scan_group_id=scan_group_id,
            raise_on_conflict=False,
        ),
        "google_alerts": _queue_source_scan(
            "google_alerts",
            run_google_alerts_scan,
            scan_mode,
            scan_group_id=scan_group_id,
            raise_on_conflict=False,
        ),
        "telegram": _queue_source_scan(
            "telegram",
            scan_telegram_channels,
            scan_mode,
            scan_group_id=scan_group_id,
            raise_on_conflict=False,
        ),
    }
    queued = [name for name, payload in results.items() if payload.get("success")]
    return {
        "success": bool(queued),
        "scan_mode": scan_mode,
        "scan_group_id": scan_group_id,
        "queued_sources": queued,
        "results": results,
    }


@app.delete("/admin/dev/mock-data")
def delete_dev_mock_data() -> dict[str, bool | int | str]:
    if settings.APP_ENV != "development":
        raise HTTPException(status_code=403, detail="Development-only endpoint")

    try:
        result = delete_mock_paste_detections()
    except ElasticsearchUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "success": True,
        "source": "mock_paste",
        "deleted": int(result["deleted"]),
    }
