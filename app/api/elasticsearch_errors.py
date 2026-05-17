from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import HTTPException

from app.storage.elastic_client import (
    DetectionNotFoundError,
    ElasticsearchQueryError,
    ElasticsearchUnavailableError,
)


logger = logging.getLogger(__name__)
T = TypeVar("T")


def run_elasticsearch_endpoint(operation: Callable[[], T], *, endpoint: str) -> T:
    try:
        return operation()
    except DetectionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": str(exc),
                "error_type": "DetectionNotFoundError",
                "endpoint": endpoint,
            },
        ) from exc
    except ElasticsearchUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "success": False,
                "error": str(exc),
                "error_type": "ElasticsearchUnavailableError",
                "endpoint": endpoint,
            },
        ) from exc
    except ElasticsearchQueryError as exc:
        root = exc.__cause__ or exc
        logger.exception("Elasticsearch query failed for %s", endpoint)
        raise HTTPException(
            status_code=502,
            detail={
                "success": False,
                "error": str(exc),
                "error_type": type(root).__name__,
                "endpoint": endpoint,
            },
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected API failure for %s", endpoint)
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "endpoint": endpoint,
            },
        ) from exc
