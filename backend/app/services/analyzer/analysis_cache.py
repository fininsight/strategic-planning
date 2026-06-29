from __future__ import annotations

import html
import json
import threading
from datetime import datetime
from pathlib import Path

from .config import ANALYSIS_VERSION, API_ORIGIN, CACHE_DIR, PROJECT_ROOT, PUBLIC_FILE_BASE, WEB_ANALYSIS_DIR
from .document_converter import viewer_file
from .g2b_document_downloader import attachment_payload, download_g2b_attachments
from .llm_analyzer import document_kind, llm_document_analysis, rule_document_analysis, summarize_notice
from .proposal_mapping_analyzer import generate_proposal_mapping
from .proposal_sheet_analyzer import generate_proposal_sheets
from .text_extractor import extract_document_text, extract_pdf_text, is_text_like_document
from app.services.storage import database

_PREPARE_LOCKS: dict[str, threading.Lock] = {}
_PREPARE_LOCKS_GUARD = threading.Lock()


def _prepare_lock(key: str) -> threading.Lock:
    with _PREPARE_LOCKS_GUARD:
        lock = _PREPARE_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PREPARE_LOCKS[key] = lock
        return lock


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
    convert_viewer: bool = True,
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
    viewer_type, viewer_path, viewer_error = viewer_file(file_path, extension, allow_convert=convert_viewer)
    should_prepare_text_fallback = (
        viewer_type == "text"
        or (viewer_type == "rhwp" and extension == ".hwpx" and is_text_like_document(file_path))
    )
    if not extract_text and should_prepare_text_fallback:
        text, page_count, extraction_method, extraction_error = extract_document_text(file_path, extension)

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
        "attachmentKey": database.attachment_key(selected),
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


def _refresh_text_viewer_documents(payload: dict) -> bool:
    changed = False
    for document in payload.get("documents", []):
        if document.get("viewerType") != "text" or document.get("documentText"):
            continue
        file_path = Path(document.get("filePath") or "")
        if not file_path.exists():
            continue
        extension = str(document.get("extension") or file_path.suffix).lower()
        if extension != ".hwpx" and not is_text_like_document(file_path):
            continue
        text, page_count, extraction_method, extraction_error = extract_document_text(file_path, extension)
        if not text:
            continue
        document["documentText"] = text
        document["textLength"] = len(text)
        document["pageCount"] = page_count
        document["extractionMethod"] = extraction_method
        document["extractionError"] = extraction_error
        document["viewerError"] = "실제 파일 내용이 XML/텍스트라 원문 텍스트로 표시합니다."
        document["analysis"] = rule_document_analysis(text, document.get("fileName", ""))
        changed = True
    return changed


def _refresh_rhwp_viewer_documents(payload: dict, bid_no: str, bid_ord: str) -> bool:
    changed = False
    for idx, document in enumerate(payload.get("documents", [])):
        extension = str(document.get("extension") or "").lower()
        if extension not in {".hwp", ".hwpx"} or document.get("viewerType") in {"pdf", "rhwp"}:
            continue
        file_path = Path(document.get("filePath") or "")
        if not file_path.exists() or is_text_like_document(file_path):
            continue

        document["viewerType"] = "rhwp"
        document["viewerPath"] = str(file_path)
        document["pdfPath"] = str(file_path)
        document["fileUrl"] = _public_or_api_file_url(bid_no, bid_ord, idx, file_path, "files")
        document["originalFileUrl"] = _public_or_api_file_url(bid_no, bid_ord, idx, file_path, "original-files")
        document["pdfUrl"] = ""
        document["viewerError"] = "PDF 변환 대신 HWP/HWPX 전용 뷰어로 표시합니다."
        changed = True
    return changed


def _document_files_state(payload: dict) -> str:
    """캐시된 파일 상태를 반환한다.
    'ok': 모든 파일이 캐시 경로에 존재
    'stale': documents는 있으나 일부 파일이 캐시 경로에 없음 (경로 불일치 또는 삭제)
    'missing': documents 자체가 없음
    """
    documents = payload.get("documents") or []
    if not documents:
        return "missing"
    for document in documents:
        file_path = Path(document.get("filePath") or "")
        viewer_path = Path(document.get("viewerPath") or document.get("pdfPath") or "")
        if not file_path.exists() or not _is_cache_path(file_path):
            return "stale"
        if document.get("viewerType") == "pdf" and (not viewer_path.exists() or not _is_cache_path(viewer_path)):
            return "stale"
    return "ok"


def _document_files_available(payload: dict) -> bool:
    """하위 호환성을 위해 유지."""
    return _document_files_state(payload) == "ok"


def _patch_document_urls(payload: dict, bid_no: str, bid_ord: str) -> dict:
    """파일이 없거나 경로가 바뀐 경우, fileUrl/fileUrl을 API 엔드포인트 URL로 교체한다."""
    import copy
    patched = copy.deepcopy(payload)
    for idx, document in enumerate(patched.get("documents", [])):
        file_path = Path(document.get("filePath") or "")
        viewer_path = Path(document.get("viewerPath") or document.get("pdfPath") or "")
        file_missing = not file_path.exists() or not _is_cache_path(file_path)
        viewer_missing = document.get("viewerType") == "pdf" and (
            not viewer_path.exists() or not _is_cache_path(viewer_path)
        )
        if file_missing:
            document["originalFileUrl"] = f"{API_ORIGIN}/api/notices/{bid_no}/{bid_ord}/original-files/{idx}"
        if viewer_missing:
            document["fileUrl"] = f"{API_ORIGIN}/api/notices/{bid_no}/{bid_ord}/files/{idx}"
            document["pdfUrl"] = document["fileUrl"]
    return patched


def prepare_notice_documents(bid_no: str, bid_ord: str) -> dict:
    """첨부파일 다운로드/변환과 뷰어 표시용 payload만 준비한다."""
    key = f"{bid_no}-{bid_ord}"
    with _prepare_lock(key):
        cache_path = WEB_ANALYSIS_DIR / f"{key}.json"

        # 1. 실제 파일까지 살아 있는 캐시만 뷰어 캐시로 인정한다.
        if cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                if payload.get("documents") and _document_files_state(payload) == "ok":
                    changed = _refresh_text_viewer_documents(payload)
                    changed = _refresh_rhwp_viewer_documents(payload, bid_no, bid_ord) or changed
                    if changed:
                        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    return payload
            except Exception:
                pass

        # 2. 캐시가 없거나 stale이면 다운로드/변환을 다시 시도한다.
        # 실패 결과는 JSON으로 저장하지 않는다. 실패 캐시가 다음 재시도를 막지 않게 하기 위함이다.
        out_dir = CACHE_DIR / key
        download_info = download_g2b_attachments(bid_no, bid_ord, out_dir)
        downloads = download_info.get("downloads") or [
            {"pdfPath": download_info["pdfPath"], "selected": download_info["selected"]}
        ]
        attachments = download_info["attachments"]
        if not downloads:
            raise RuntimeError("분석 대상 첨부파일을 찾지 못했습니다.")

        # 3. 텍스트 추출이나 LLM 없이 순수하게 문서/뷰어 정보만 만든다.
        documents = []
        for idx, item in enumerate(downloads):
            document, _ = _document_payload(
                idx,
                bid_no,
                bid_ord,
                item,
                extract_text=False,
                analyze_document=False,
                convert_viewer=False,
            )
            documents.append(document)

        primary = documents[0]
        result = {
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

        WEB_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        database.upsert_attachments(bid_no, bid_ord, attachments)
        database.record_downloads(bid_no, bid_ord, downloads)
        database.record_document_payloads(bid_no, bid_ord, documents, ANALYSIS_VERSION)
        database.record_notice_analysis(bid_no, bid_ord, result, ANALYSIS_VERSION)
        return result


def analyze_notice(bid_no: str, bid_ord: str) -> dict:
    """백그라운드에서 문서 텍스트 추출과 LLM 요약을 수행한다."""
    key = f"{bid_no}-{bid_ord}"
    cache_path = WEB_ANALYSIS_DIR / f"{key}.json"

    # 1. 뷰어용 문서 정보를 무조건 확보 (캐시가 있으면 0.1초 컷, 없으면 다운로드)
    payload = prepare_notice_documents(bid_no, bid_ord)
    # 2. 이미 LLM 분석이 완료된 최신 버전이라면 그냥 반환
    if payload.get("status") == "completed" and payload.get("summary", {}).get("analysisVersion") == ANALYSIS_VERSION:
        if _refresh_rhwp_viewer_documents(payload, bid_no, bid_ord):
            cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            database.record_document_payloads(bid_no, bid_ord, payload.get("documents", []), ANALYSIS_VERSION)
            database.record_notice_analysis(bid_no, bid_ord, payload, ANALYSIS_VERSION)
        return payload

    # 3. 문서 텍스트 추출 및 문서별 LLM 분석
    combined_text_parts = []
    for document in payload.get("documents", []):
        file_path = Path(document.get("filePath") or "")
        viewer_path = Path(document.get("viewerPath") or "")
        extension = str(document.get("extension") or "").lower()

        if extension in {".hwp", ".hwpx"} and file_path.exists():
            viewer_type, converted_viewer_path, viewer_error = viewer_file(file_path, extension, allow_convert=True)
            document["viewerType"] = viewer_type
            document["viewerPath"] = str(converted_viewer_path)
            document["pdfPath"] = str(converted_viewer_path)
            document["viewerError"] = viewer_error
            document["fileUrl"] = _public_or_api_file_url(
                bid_no, bid_ord, int(document.get("id", "0")), converted_viewer_path, "files"
            )
            document["pdfUrl"] = document["fileUrl"] if viewer_type == "pdf" else ""
            viewer_path = converted_viewer_path

        # 텍스트 추출
        text = ""
        if viewer_path.exists() and viewer_path.suffix.lower() == ".pdf":
            try:
                text, page_count = extract_pdf_text(viewer_path)
                document["documentText"] = text
                document["textLength"] = len(text)
                document["pageCount"] = page_count
                document["extractionMethod"] = "converted-pdf-text"
            except Exception as e:
                document["extractionError"] = str(e)
        elif file_path.exists():
            try:
                text, page_count, _, _ = extract_document_text(file_path, document.get("extension", ""))
                document["documentText"] = text
                document["textLength"] = len(text)
                document["pageCount"] = page_count
                document["extractionMethod"] = "extract_document_text"
            except Exception as e:
                document["extractionError"] = str(e)

        # 문서별 LLM 분석
        document["analysis"] = llm_document_analysis(text, document.get("fileName", ""))
        combined_text_parts.append(text)

    # 4. 전체 공고 요약 및 제안서 생성
    primary = payload["documents"][0]
    payload["documentText"] = primary["documentText"]
    payload["source"]["textLength"] = primary["textLength"]
    payload["source"]["pageCount"] = primary["pageCount"]
    payload["source"]["extractionMethod"] = primary["extractionMethod"]

    payload["summary"] = summarize_notice("\n\n".join(combined_text_parts))
    payload["proposalSheets"] = generate_proposal_sheets(payload, use_llm=True)
    payload["proposalMapping"] = generate_proposal_mapping(payload)
    payload["status"] = "completed"
    payload["analyzedAt"] = datetime.now().isoformat()

    # 5. 캐시에 저장하고 최종 반환
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    database.record_document_payloads(bid_no, bid_ord, payload.get("documents", []), ANALYSIS_VERSION)
    database.record_notice_analysis(bid_no, bid_ord, payload, ANALYSIS_VERSION)
    return payload
