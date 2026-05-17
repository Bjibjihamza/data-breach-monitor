from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["dashboard"])

_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
_FRONTEND_INDEX = _FRONTEND_DIST / "index.html"
_DASHBOARD_HTML = Path(__file__).resolve().parent.parent / "templates" / "dashboard.html"


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    if _FRONTEND_INDEX.exists():
        return HTMLResponse(_FRONTEND_INDEX.read_text(encoding="utf-8"))
    return HTMLResponse(_DASHBOARD_HTML.read_text(encoding="utf-8"))


@router.get("/dashboard/{path:path}", response_class=HTMLResponse, include_in_schema=False)
def dashboard_spa(path: str) -> HTMLResponse:
    if _FRONTEND_INDEX.exists():
        return HTMLResponse(_FRONTEND_INDEX.read_text(encoding="utf-8"))
    return HTMLResponse(_DASHBOARD_HTML.read_text(encoding="utf-8"))
