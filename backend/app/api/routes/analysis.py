from __future__ import annotations

import sys
import traceback

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.errors import api_error

router = APIRouter(prefix="/api/notices/{bid_no}/{bid_ord}", tags=["analysis"])


def load_notice_analysis(bid_no: str, bid_ord: str) -> dict:
    from app.services.analyzer.analysis_cache import analyze_notice

    return analyze_notice(bid_no, bid_ord)


@router.get("/documents")
def prepare_documents(bid_no: str, bid_ord: str) -> JSONResponse:
    try:
        from app.services.analyzer.analysis_cache import prepare_notice_documents

        return JSONResponse(content=prepare_notice_documents(bid_no, bid_ord))
    except Exception as exc:
        print(f"[documents ERROR] {bid_no}/{bid_ord}: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return api_error(500, "documents_failed", exc)


@router.get("/analysis")
def get_analysis(bid_no: str, bid_ord: str) -> JSONResponse:
    try:
        return JSONResponse(content=load_notice_analysis(bid_no, bid_ord))
    except Exception as exc:
        return api_error(500, "analysis_failed", exc)


@router.get("/proposal-analysis")
def get_proposal_analysis(bid_no: str, bid_ord: str) -> JSONResponse:
    try:
        return JSONResponse(content=load_notice_analysis(bid_no, bid_ord).get("proposalSheets", {}))
    except Exception as exc:
        return api_error(500, "proposal_analysis_failed", exc)


@router.get("/proposal-mapping")
def get_proposal_mapping(bid_no: str, bid_ord: str) -> JSONResponse:
    try:
        from app.services.analyzer.proposal_mapping_analyzer import generate_proposal_mapping

        return JSONResponse(content=generate_proposal_mapping(load_notice_analysis(bid_no, bid_ord)))
    except Exception as exc:
        return api_error(500, "proposal_mapping_failed", exc)


@router.get("/market-research")
def get_market_research_endpoint(bid_no: str, bid_ord: str, refresh: str = "0") -> JSONResponse:
    try:
        from app.services.analyzer.analysis_cache import get_market_research

        should_refresh = refresh.lower() in {"1", "true", "yes"}
        return JSONResponse(content=get_market_research(bid_no, bid_ord, refresh=should_refresh))
    except Exception as exc:
        return api_error(500, "market_research_failed", exc)
