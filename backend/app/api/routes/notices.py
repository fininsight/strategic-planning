from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.errors import api_error
from app.core.config import NOTICES_JSON
from app.services.storage import database

router = APIRouter(prefix="/api", tags=["notices"])


@router.get("/notices")
def list_notices() -> JSONResponse:
    payload = database.load_dashboard_payload_from_db()
    if payload:
        return JSONResponse(content=payload)
    try:
        return JSONResponse(content=json.loads(NOTICES_JSON.read_text(encoding="utf-8")))
    except Exception as exc:
        return api_error(500, "notices_failed", exc)
