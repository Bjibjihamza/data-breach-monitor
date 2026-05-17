from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.elasticsearch_errors import run_elasticsearch_endpoint
from app.schemas.detection_review import ALLOWED_DETECTION_STATUSES, DetectionListResponse, DetectionStatusUpdate
from app.storage.elastic_client import (
    DEFAULT_DETECTION_LIST_LIMIT,
    MAX_DETECTION_LIST_LIMIT,
    list_detections,
    update_detection_status,
)


router = APIRouter(tags=["detections"])


@router.get("/detections", response_model=DetectionListResponse)
def get_detections(
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
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_DETECTION_LIST_LIMIT, ge=1, le=MAX_DETECTION_LIST_LIMIT),
) -> DetectionListResponse:
    result = run_elasticsearch_endpoint(
        lambda: list_detections(
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
            offset=offset,
            limit=limit,
        ),
        endpoint="/detections",
    )
    return DetectionListResponse(**result)


@router.patch("/detections/{detection_hash}/status")
def patch_detection_status(detection_hash: str, body: DetectionStatusUpdate) -> dict[str, object]:
    if body.status not in ALLOWED_DETECTION_STATUSES:
        allowed = ", ".join(sorted(ALLOWED_DETECTION_STATUSES))
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": f"Invalid status '{body.status}'. Allowed values: {allowed}",
                "error_type": "ValidationError",
                "endpoint": f"/detections/{detection_hash}/status",
            },
        )

    updated = run_elasticsearch_endpoint(
        lambda: update_detection_status(
            detection_hash,
            status=body.status,
            review_note=body.review_note,
            reviewed_by=body.reviewed_by,
        ),
        endpoint=f"/detections/{detection_hash}/status",
    )
    return {
        "success": True,
        "detection_hash": str(updated.get("detection_hash") or detection_hash),
        "status": str(updated.get("status") or body.status),
    }
