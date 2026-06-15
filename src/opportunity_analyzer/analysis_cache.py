from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

from .config import ANALYSIS_VERSION, API_ORIGIN, CACHE_DIR, WEB_ANALYSIS_DIR
from .document_converter import viewer_file
from .g2b_document_downloader import attachment_payload, download_g2b_attachments
from .llm_analyzer import document_kind, llm_document_analysis, summarize_notice
from .proposal_sheet_analyzer import generate_proposal_sheets
from .text_extractor import extract_document_text, extract_pdf_text


def _document_payload(
    idx: int,
    bid_no: str,
    bid_ord: str,
    item: dict,
) -> tuple[dict, str]:
    file_path = Path(item.get("filePath") or item["pdfPath"])
    selected = item["selected"]
    file_name = html.unescape(selected.get("orgnlAtchFileNm", file_path.name))
    extension = str(selected.get("fileExtnNm") or file_path.suffix).lower()
    text, page_count, extraction_method, extraction_error = extract_document_text(file_path, extension)
    viewer_type, viewer_path, viewer_error = viewer_file(file_path, extension)

    if viewer_type == "pdf":
        try:
            viewer_text, viewer_page_count = extract_pdf_text(viewer_path)
            if not page_count:
                page_count = viewer_page_count
            if extension in {".hwp", ".hwpx"} and len(viewer_text) > len(text):
                text = viewer_text
                page_count = viewer_page_count
                extraction_method = "converted-pdf-text"
                extraction_error = ""
        except Exception:
            pass

    combined_text = f"[{file_name}]\n{text[:9000]}" if text else (
        f"[{file_name}]\n텍스트 추출 불가: {extraction_error or '내용 확인 필요'}"
    )
    document = {
        "id": str(idx),
        "fileName": file_name,
        "extension": extension,
        "docType": document_kind(file_name),
        "viewerType": viewer_type,
        "fileUrl": f"{API_ORIGIN}/api/notices/{bid_no}/{bid_ord}/files/{idx}",
        "originalFileUrl": f"{API_ORIGIN}/api/notices/{bid_no}/{bid_ord}/original-files/{idx}",
        "pdfUrl": f"{API_ORIGIN}/api/notices/{bid_no}/{bid_ord}/files/{idx}" if viewer_type == "pdf" else "",
        "filePath": str(file_path),
        "viewerPath": str(viewer_path),
        "pdfPath": str(viewer_path),
        "pageCount": page_count,
        "textLength": len(text),
        "extractionMethod": extraction_method,
        "extractionError": extraction_error,
        "viewerError": viewer_error,
        "documentText": text,
        "analysis": llm_document_analysis(text, file_name),
    }
    return document, combined_text


def _refresh_converted_pdf_text(payload: dict) -> bool:
    changed = False
    for document in payload.get("documents", []):
        extension = str(document.get("extension") or "").lower()
        viewer_path = Path(document.get("viewerPath") or "")
        current_text = document.get("documentText") or ""
        if extension not in {".hwp", ".hwpx"} or not viewer_path.exists() or viewer_path.suffix.lower() != ".pdf":
            continue
        try:
            viewer_text, page_count = extract_pdf_text(viewer_path)
        except Exception:
            continue
        if len(viewer_text) <= len(current_text) and "<표>" not in current_text:
            continue
        document["documentText"] = viewer_text
        document["textLength"] = len(viewer_text)
        document["pageCount"] = page_count
        document["extractionMethod"] = "converted-pdf-text"
        document["extractionError"] = ""
        changed = True
    return changed


def analyze_notice(bid_no: str, bid_ord: str) -> dict:
    key = f"{bid_no}-{bid_ord}"
    cache_path = WEB_ANALYSIS_DIR / f"{key}.json"
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if payload.get("documents"):
            proposal_sheets = payload.get("proposalSheets") or {}
            if proposal_sheets.get("analysisVersion") != ANALYSIS_VERSION:
                _refresh_converted_pdf_text(payload)
                payload["proposalSheets"] = generate_proposal_sheets(payload)
                cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return payload
        summary = payload.get("summary", {})
        if (
            summary.get("insightSource") == "llm"
            and summary.get("analysisVersion") == ANALYSIS_VERSION
            and payload.get("documents")
            and payload.get("proposalSheets")
        ):
            return payload

    out_dir = CACHE_DIR / key
    download_info = download_g2b_attachments(bid_no, bid_ord, out_dir)
    downloads = download_info.get("downloads") or [
        {"pdfPath": download_info["pdfPath"], "selected": download_info["selected"]}
    ]
    attachments = download_info["attachments"]

    documents = []
    combined_text_parts = []
    for idx, item in enumerate(downloads):
        document, combined_text = _document_payload(idx, bid_no, bid_ord, item)
        documents.append(document)
        combined_text_parts.append(combined_text)

    primary = documents[0]
    payload = {
        "bidNtceNo": bid_no,
        "bidNtceOrd": bid_ord,
        "analyzedAt": datetime.now().isoformat(),
        "status": "completed",
        "source": {
            "fileName": primary["fileName"],
            "pdfPath": primary["filePath"],
            "pageCount": primary["pageCount"],
            "textLength": primary["textLength"],
            "extractionMethod": primary["extractionMethod"],
        },
        "attachments": [attachment_payload(item) for item in attachments],
        "documents": documents,
        "documentText": primary["documentText"],
        "summary": summarize_notice("\n\n".join(combined_text_parts)),
    }
    payload["proposalSheets"] = generate_proposal_sheets(payload)
    WEB_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
