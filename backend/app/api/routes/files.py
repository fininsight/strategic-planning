from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.api.errors import api_error

router = APIRouter(prefix="/api/notices/{bid_no}/{bid_ord}", tags=["files"])

CHUNK_SIZE = 1024 * 1024


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


async def _iter_file(file_path: Path, start: int, end: int):
    with file_path.open("rb") as file:
        file.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = file.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _parse_range(range_header: str | None, file_size: int) -> tuple[int, int, int] | None:
    if not range_header:
        return None
    unit, _, value = range_header.partition("=")
    if unit.strip().lower() != "bytes" or "," in value:
        raise HTTPException(status_code=416, detail={"error": "range_not_satisfiable"})

    start_text, _, end_text = value.strip().partition("-")
    if not start_text and not end_text:
        raise HTTPException(status_code=416, detail={"error": "range_not_satisfiable"})

    if start_text:
        start = int(start_text)
        end = int(end_text) if end_text else file_size - 1
    else:
        suffix_size = int(end_text)
        start = max(file_size - suffix_size, 0)
        end = file_size - 1

    if start < 0 or end < start or start >= file_size:
        raise HTTPException(status_code=416, detail={"error": "range_not_satisfiable"})
    return start, min(end, file_size - 1), file_size


def send_document_file(
    request: Request,
    bid_no: str,
    bid_ord: str,
    document_id: str,
    *,
    original: bool,
) -> Response:
    try:
        file_path, content_type = resolve_document_file(bid_no, bid_ord, document_id, original=original)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content=detail)
    except Exception as exc:
        return api_error(500, "file_failed", exc)

    disposition = "inline" if content_type in {"application/pdf", "text/html"} else "attachment"
    file_size = file_path.stat().st_size
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(file_path.name)}",
    }

    try:
        byte_range = _parse_range(request.headers.get("range"), file_size)
    except ValueError:
        return JSONResponse(
            status_code=416,
            content={"error": "range_not_satisfiable"},
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    if byte_range:
        start, end, total = byte_range
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        headers["Content-Length"] = str(end - start + 1)
        return StreamingResponse(
            _iter_file(file_path, start, end),
            status_code=206,
            media_type=content_type,
            headers=headers,
        )

    headers["Content-Length"] = str(file_size)
    return StreamingResponse(
        _iter_file(file_path, 0, file_size - 1),
        media_type=content_type,
        headers=headers,
    )


@router.get("/files/{document_id}")
def get_viewer_file(request: Request, bid_no: str, bid_ord: str, document_id: str) -> Response:
    return send_document_file(request, bid_no, bid_ord, document_id, original=False)


@router.get("/original-files/{document_id}")
def get_original_file(request: Request, bid_no: str, bid_ord: str, document_id: str) -> Response:
    return send_document_file(request, bid_no, bid_ord, document_id, original=True)
