from __future__ import annotations

import sys
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.errors import api_error

router = APIRouter(prefix="/api/notices/{bid_no}/{bid_ord}", tags=["analysis"])
_MARKET_RESEARCH_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_MARKET_RESEARCH_JOBS: dict[str, dict] = {}
_MARKET_RESEARCH_JOBS_LOCK = threading.Lock()


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
        from app.services.analyzer.analysis_cache import get_market_research, load_cached_market_research

        should_refresh = refresh.lower() in {"1", "true", "yes"}
        job_key = f"{bid_no}-{bid_ord}"

        cached = None if should_refresh else load_cached_market_research(bid_no, bid_ord)
        if cached:
            return JSONResponse(content=cached)

        with _MARKET_RESEARCH_JOBS_LOCK:
            job = _MARKET_RESEARCH_JOBS.get(job_key)
            if job and job.get("status") == "completed" and isinstance(job.get("result"), dict) and not should_refresh:
                return JSONResponse(content=job["result"])
            if job and job.get("status") == "completed" and not should_refresh:
                cached = load_cached_market_research(bid_no, bid_ord)
                if cached:
                    return JSONResponse(content=cached)
            if job and job.get("status") in {"queued", "processing"}:
                return JSONResponse(content=_market_research_processing_payload(bid_no, bid_ord, job))

            job = {
                "status": "queued",
                "startedAt": datetime.now(timezone.utc).isoformat(),
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "refresh": should_refresh,
                "error": "",
            }
            _MARKET_RESEARCH_JOBS[job_key] = job
            print(f"[market-research] queued {job_key} refresh={should_refresh}", file=sys.stderr)
            _MARKET_RESEARCH_EXECUTOR.submit(_run_market_research_job, bid_no, bid_ord, should_refresh)
            return JSONResponse(content=_market_research_processing_payload(bid_no, bid_ord, job))
    except Exception as exc:
        return api_error(500, "market_research_failed", exc)


def _run_market_research_job(bid_no: str, bid_ord: str, refresh: bool) -> None:
    from app.services.analyzer.analysis_cache import get_market_research

    job_key = f"{bid_no}-{bid_ord}"
    with _MARKET_RESEARCH_JOBS_LOCK:
        job = _MARKET_RESEARCH_JOBS.setdefault(job_key, {})
        job["status"] = "processing"
        job["updatedAt"] = datetime.now(timezone.utc).isoformat()
    print(f"[market-research] processing {job_key} refresh={refresh}", file=sys.stderr)
    try:
        result = get_market_research(bid_no, bid_ord, refresh=refresh)
        with _MARKET_RESEARCH_JOBS_LOCK:
            job = _MARKET_RESEARCH_JOBS.setdefault(job_key, {})
            job["status"] = "completed"
            job["updatedAt"] = datetime.now(timezone.utc).isoformat()
            job["error"] = ""
            job["result"] = result
        source_mode = result.get("sourceMode") if isinstance(result, dict) else ""
        print(f"[market-research] completed {job_key} sourceMode={source_mode}", file=sys.stderr)
    except Exception as exc:
        with _MARKET_RESEARCH_JOBS_LOCK:
            job = _MARKET_RESEARCH_JOBS.setdefault(job_key, {})
            job["status"] = "failed"
            job["updatedAt"] = datetime.now(timezone.utc).isoformat()
            job["error"] = str(exc)
        print(f"[market-research] failed {job_key}: {exc}", file=sys.stderr)


def _market_research_processing_payload(bid_no: str, bid_ord: str, job: dict) -> dict:
    return {
        "id": f"{bid_no}-{bid_ord}",
        "generatedAt": job.get("updatedAt") or datetime.now(timezone.utc).isoformat(),
        "projectName": "시장·경쟁 리서치 생성 중",
        "sourceMode": "processing",
        "status": job.get("status") or "processing",
        "message": "시장·경쟁 리서치를 백그라운드에서 생성하고 있습니다.",
        "startedAt": job.get("startedAt", ""),
        "updatedAt": job.get("updatedAt", ""),
        "error": job.get("error", ""),
    }
