from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response

from app.api.errors import api_error

router = APIRouter(prefix="/api/notices/{bid_no}/{bid_ord}", tags=["files"])


def resolve_document_file(bid_no: str, bid_ord: str, document_id: str, *, original: bool) -> tuple[Path, str]:
    from app.services.analyzer.analysis_cache import prepare_notice_documents
    from app.services.analyzer.config import CACHE_DIR

    payload = prepare_notice_documents(bid_no, bid_ord)
    document = next((item for item in payload.get("documents", []) if item.get("id") == document_id), None)
    if document is None:
        raise HTTPException(status_code=404, detail={"error": "document_not_found"})

    path_key = "filePath" if original else "viewerPath"
    file_path = Path(document.get(path_key) or document.get("filePath") or document["pdfPath"]).resolve()
    try:
        file_path.relative_to(CACHE_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"error": "file_not_found"}) from exc
    if not file_path.exists():
        raise HTTPException(status_code=404, detail={"error": "file_not_found"})
    return file_path, mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"


def send_document_file(bid_no: str, bid_ord: str, document_id: str, *, original: bool) -> Response:
    try:
        file_path, content_type = resolve_document_file(bid_no, bid_ord, document_id, original=original)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content=detail)
    except Exception as exc:
        return api_error(500, "file_failed", exc)

    disposition = "inline" if content_type in {"application/pdf", "text/html"} else "attachment"
    return FileResponse(
        file_path,
        media_type=content_type,
        headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(file_path.name)}"},
    )


@router.get("/files/{document_id}")
def get_viewer_file(bid_no: str, bid_ord: str, document_id: str) -> Response:
    return send_document_file(bid_no, bid_ord, document_id, original=False)


@router.get("/original-files/{document_id}")
def get_original_file(bid_no: str, bid_ord: str, document_id: str) -> Response:
    return send_document_file(bid_no, bid_ord, document_id, original=True)
