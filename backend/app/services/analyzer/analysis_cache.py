from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

from .config import ANALYSIS_VERSION, API_ORIGIN, CACHE_DIR, PROJECT_ROOT, PUBLIC_FILE_BASE, WEB_ANALYSIS_DIR
from .document_converter import viewer_file
from .g2b_document_downloader import attachment_payload, download_g2b_attachments
from .llm_analyzer import document_kind, llm_document_analysis, rule_document_analysis, summarize_notice
from .proposal_sheet_analyzer import generate_proposal_sheets
from .text_extractor import extract_document_text, extract_pdf_text


def _is_cache_path(path: Path) -> bool:
    try:
        path.resolve().relative_to(CACHE_DIR.resolve())
        return True
    except ValueError:
        return False


def _document_payload(
    idx: int,
    bid_no: str,
    bid_ord: str,
    item: dict,
    *,
    extract_text: bool = True,
    analyze_document: bool = True,
) -> tuple[dict, str]:
    file_path = Path(item.get("filePath") or item["pdfPath"])
    selected = item["selected"]
    file_name = html.unescape(selected.get("orgnlAtchFileNm", file_path.name))
    extension = str(selected.get("fileExtnNm") or file_path.suffix).lower()
    text = ""
    page_count = 0
    extraction_method = "deferred"
    extraction_error = ""
    if extract_text:
        text, page_count, extraction_method, extraction_error = extract_document_text(file_path, extension)
    viewer_type, viewer_path, viewer_error = viewer_file(file_path, extension)

    if extract_text and viewer_type == "pdf":
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

    file_url = _public_or_api_file_url(bid_no, bid_ord, idx, file_path, "original-files")
    viewer_url = _public_or_api_file_url(bid_no, bid_ord, idx, viewer_path, "files")

    combined_text = f"[{file_name}]\n{text[:9000]}" if text else (
        f"[{file_name}]\n텍스트 추출 불가: {extraction_error or '내용 확인 필요'}"
    )
    document = {
        "id": str(idx),
        "fileName": file_name,
        "extension": extension,
        "docType": document_kind(file_name),
        "viewerType": viewer_type,
        "fileUrl": viewer_url,
        "originalFileUrl": file_url,
        "pdfUrl": viewer_url if viewer_type == "pdf" else "",
        "filePath": str(file_path),
        "viewerPath": str(viewer_path),
        "pdfPath": str(viewer_path),
        "pageCount": page_count,
        "textLength": len(text),
        "extractionMethod": extraction_method,
        "extractionError": extraction_error,
        "viewerError": viewer_error,
        "documentText": text,
        "analysis": llm_document_analysis(text, file_name) if analyze_document else rule_document_analysis(text, file_name),
    }
    return document, combined_text


def _quick_notice_summary(primary: dict, documents: list[dict]) -> dict:
    return {
        "title": primary.get("fileName", "공고서 확인"),
        "budget": "공고서 기준 확인",
        "deadline": "공고서 기준 확인",
        "method": "공고서 기준 확인",
        "requirements": [
            {"label": "입찰 자격", "text": "첨부파일 원문에서 확인 필요"},
            {"label": "과업 범위", "text": "제안요청서/과업지시서 원문에서 확인 필요"},
        ],
        "strength": "첨부파일 캐시를 사용해 문서 뷰어를 우선 표시했습니다.",
        "risk": "AI 심층 분석 전에는 원문 기준으로 주요 조건을 확인해야 합니다.",
        "opportunity": "문서별 탭에서 공고서와 제안요청서를 먼저 검토할 수 있습니다.",
        "timeline": [
            {"label": "공고 상세 일정", "date": "공고서 원문 기준 확인"},
        ],
        "analysisVersion": ANALYSIS_VERSION,
        "insightSource": "rule",
        "documentCount": len(documents),
    }


def _public_or_api_file_url(bid_no: str, bid_ord: str, idx: int, file_path: Path, api_kind: str) -> str:
    try:
        relative = file_path.resolve().relative_to((PROJECT_ROOT / "frontend" / "public").resolve())
        return f"/{relative.as_posix()}"
    except ValueError:
        pass
    if PUBLIC_FILE_BASE:
        try:
            relative = file_path.resolve().relative_to(PROJECT_ROOT.resolve())
            return f"{PUBLIC_FILE_BASE.rstrip('/')}/{relative.as_posix()}"
        except ValueError:
            return f"{PUBLIC_FILE_BASE.rstrip('/')}/{file_path.name}"
    return f"{API_ORIGIN}/api/notices/{bid_no}/{bid_ord}/{api_kind}/{idx}"


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


def _document_files_available(payload: dict) -> bool:
    documents = payload.get("documents") or []
    if not documents:
        return False
    for document in documents:
        file_path = Path(document.get("filePath") or "")
        viewer_path = Path(document.get("viewerPath") or document.get("pdfPath") or "")
        if not file_path.exists() or not _is_cache_path(file_path):
            return False
        if document.get("viewerType") == "pdf" and (not viewer_path.exists() or not _is_cache_path(viewer_path)):
            return False
    return True


def prepare_notice_documents(bid_no: str, bid_ord: str) -> dict:
    """첨부파일 다운로드/변환과 뷰어 표시용 payload만 준비한다."""
    key = f"{bid_no}-{bid_ord}"
    cache_path = WEB_ANALYSIS_DIR / f"{key}.json"
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if payload.get("documents") and _document_files_available(payload):
            return payload

    out_dir = CACHE_DIR / key
    download_info = download_g2b_attachments(bid_no, bid_ord, out_dir)
    downloads = download_info.get("downloads") or [
        {"pdfPath": download_info["pdfPath"], "selected": download_info["selected"]}
    ]
    attachments = download_info["attachments"]

    documents = []
    for idx, item in enumerate(downloads):
        document, _ = _document_payload(
            idx,
            bid_no,
            bid_ord,
            item,
            extract_text=False,
            analyze_document=False,
        )
        documents.append(document)

    primary = documents[0]
    return {
        "bidNtceNo": bid_no,
        "bidNtceOrd": bid_ord,
        "analyzedAt": datetime.now().isoformat(),
        "status": "documents_ready",
        "source": {
            "fileName": primary["fileName"],
            "pdfPath": primary["viewerPath"],
            "pageCount": primary["pageCount"],
            "textLength": primary["textLength"],
            "extractionMethod": primary["extractionMethod"],
        },
        "attachments": [attachment_payload(item) for item in attachments],
        "documents": documents,
        "documentText": "",
        "summary": _quick_notice_summary(primary, documents),
    }


def analyze_notice(bid_no: str, bid_ord: str) -> dict:
    key = f"{bid_no}-{bid_ord}"
    cache_path = WEB_ANALYSIS_DIR / f"{key}.json"
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if payload.get("documents") and _document_files_available(payload):
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
    quick = bool(download_info.get("cacheHit"))

    documents = []
    combined_text_parts = []
    for idx, item in enumerate(downloads):
        item["_quick"] = quick
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
        "summary": _quick_notice_summary(primary, documents) if quick else summarize_notice("\n\n".join(combined_text_parts)),
    }
    payload["proposalSheets"] = generate_proposal_sheets(payload, use_llm=not quick)
    WEB_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
