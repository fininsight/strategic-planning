from __future__ import annotations

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from app.api.errors import api_error
from app.schemas import ChecklistStateRequest, ChecklistStateResponse
from app.services.storage import database

router = APIRouter(prefix="/api/notices/{bid_no}/{bid_ord}", tags=["checklist"])


@router.get("/checklist-state", response_model=ChecklistStateResponse)
def get_checklist_state(bid_no: str, bid_ord: str) -> JSONResponse:
    try:
        return JSONResponse(content=database.load_checklist_state(bid_no, bid_ord))
    except Exception as exc:
        return api_error(500, "checklist_state_failed", exc)


@router.put("/checklist-state")
@router.post("/checklist-state")
def save_checklist_state(
    bid_no: str,
    bid_ord: str,
    payload: ChecklistStateRequest = Body(default_factory=ChecklistStateRequest),
) -> JSONResponse:
    try:
        return JSONResponse(content=database.save_checklist_state(bid_no, bid_ord, payload.checks))
    except Exception as exc:
        return api_error(500, "checklist_state_save_failed", exc)
