from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select

from app.db.session import is_enabled, session_scope
from app.models import DocumentAnalysis, DocumentExtraction, NoticeAnalysis
from app.repositories.attachment_repository import get_or_create_attachment, upsert_attachment_file
from app.repositories.notice_repository import upsert_notice_in_session


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _as_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _document_selected_payload(document: dict) -> dict:
    return {
        "attachmentKey": document.get("attachmentKey"),
        "orgnlAtchFileNm": document.get("fileName"),
        "fileExtnNm": document.get("extension"),
        "fileSz": document.get("textLength") or 0,
    }


def _analysis_type(document: dict) -> str:
    analysis = document.get("analysis") or {}
    if isinstance(analysis, dict):
        return _as_text(analysis.get("analysisSource"), "rule")
    return "rule"


def _analysis_error(document: dict) -> Optional[str]:
    analysis = document.get("analysis") or {}
    if isinstance(analysis, dict):
        error = _as_text(analysis.get("analysisError"))
        return error or None
    return None


def _record_document_analysis(session, attachment_id: int, document: dict, analysis_version: int, now: datetime) -> None:
    analysis_payload = document.get("analysis") or {}
    analysis_type = _analysis_type(document)
    existing = session.execute(
        select(DocumentAnalysis).where(
            DocumentAnalysis.attachment_id == attachment_id,
            DocumentAnalysis.analysis_version == analysis_version,
            DocumentAnalysis.analysis_type == analysis_type,
        )
    ).scalar_one_or_none()
    status = "analyzed" if analysis_payload else "pending"
    if existing is None:
        existing = DocumentAnalysis(
            attachment_id=attachment_id,
            analysis_version=analysis_version,
            analysis_type=analysis_type,
            analysis_payload=analysis_payload if isinstance(analysis_payload, dict) else {},
            status=status,
            error=_analysis_error(document),
            analyzed_at=now,
        )
        session.add(existing)
    else:
        existing.analysis_payload = analysis_payload if isinstance(analysis_payload, dict) else {}
        existing.status = status
        existing.error = _analysis_error(document)
        existing.analyzed_at = now


def record_document_payloads(bid_no: str, bid_ord: str, documents: list[dict], analysis_version: int) -> Optional[int]:
    if not is_enabled():
        return None
    with session_scope() as session:
        notice = upsert_notice_in_session(session, {"bidNtceNo": bid_no, "bidNtceOrd": bid_ord})
        count = 0
        now = datetime.now(timezone.utc)
        for document in documents:
            attachment = get_or_create_attachment(
                session,
                notice,
                _document_selected_payload(document),
                status="analyzed" if document.get("analysis") else "extracted",
            )
            viewer_path = _as_text(document.get("viewerPath") or document.get("pdfPath"))
            if viewer_path:
                upsert_attachment_file(
                    session,
                    int(attachment.id),
                    file_role="viewer",
                    storage_path=viewer_path,
                    size=0,
                    status="ready" if not document.get("viewerError") else "failed",
                    error=_as_text(document.get("viewerError")),
                )
            extraction = DocumentExtraction(
                attachment_id=int(attachment.id),
                text_length=_as_int(document.get("textLength")),
                page_count=_as_int(document.get("pageCount")),
                extraction_method=_as_text(document.get("extractionMethod")),
                status="extracted" if document.get("documentText") else "pending",
                error=_as_text(document.get("extractionError")) or None,
                extracted_at=now,
            )
            session.add(extraction)
            _record_document_analysis(session, int(attachment.id), document, analysis_version, now)
            count += 1
        return count


def record_notice_analysis(bid_no: str, bid_ord: str, payload: dict, analysis_version: int) -> Optional[bool]:
    if not is_enabled():
        return None
    status = "analysis_ready" if payload.get("status") == "completed" else _as_text(payload.get("status"), "files_ready")
    with session_scope() as session:
        notice = upsert_notice_in_session(
            session,
            {
                "bidNtceNo": bid_no,
                "bidNtceOrd": bid_ord,
                "status": status,
            },
        )
        now = datetime.now(timezone.utc)
        existing = session.execute(
            select(NoticeAnalysis).where(
                NoticeAnalysis.notice_id == notice.id,
                NoticeAnalysis.analysis_version == analysis_version,
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = NoticeAnalysis(
                notice_id=int(notice.id),
                analysis_version=analysis_version,
                summary_payload=payload.get("summary") or {},
                proposal_sheets_payload=payload.get("proposalSheets") or {},
                status=payload.get("status") or "completed",
                error=None,
                analyzed_at=now,
            )
            session.add(existing)
        else:
            existing.summary_payload = payload.get("summary") or {}
            existing.proposal_sheets_payload = payload.get("proposalSheets") or {}
            existing.status = payload.get("status") or "completed"
            existing.error = None
            existing.analyzed_at = now
        return True
