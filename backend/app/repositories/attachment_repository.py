from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import is_enabled, session_scope
from app.core.keys import attachment_key
from app.models import AttachmentFile, Notice, NoticeAttachment
from app.repositories.notice_repository import upsert_notice_in_session


def _as_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _attachment_payload(item: dict) -> dict:
    return {
        "attachment_key": attachment_key(item),
        "original_file_name": _as_text(item.get("orgnlAtchFileNm") or item.get("fileName")),
        "extension": _as_text(item.get("fileExtnNm") or item.get("extension")),
        "size": _as_int(item.get("fileSz") or item.get("size")),
        "kind_code": _as_text(item.get("atchFileKndCd") or item.get("kindCode")),
        "source_download_url": _as_text(item.get("downloadUrl") or item.get("url")),
        "source_payload": item,
    }


def _status_after_download(existing: Optional[str]) -> str:
    if existing in {"analyzed", "extracted"}:
        return existing
    return "downloaded"


def get_or_create_attachment(
    session: Session,
    notice: Notice,
    selected: dict,
    *,
    status: str = "discovered",
    preserve_analyzed_status: bool = False,
) -> NoticeAttachment:
    payload = _attachment_payload(selected)
    attachment = session.execute(
        select(NoticeAttachment).where(
            NoticeAttachment.notice_id == notice.id,
            NoticeAttachment.attachment_key == payload["attachment_key"],
        )
    ).scalar_one_or_none()
    if attachment is None:
        attachment = NoticeAttachment(
            notice_id=notice.id,
            attachment_key=payload["attachment_key"],
            original_file_name=payload["original_file_name"],
            extension=payload["extension"],
            size=payload["size"],
            kind_code=payload["kind_code"],
            source_download_url=payload["source_download_url"],
            source_payload=payload["source_payload"],
            status=status,
        )
        session.add(attachment)
        session.flush()
        return attachment

    attachment.original_file_name = payload["original_file_name"]
    attachment.extension = payload["extension"]
    attachment.size = payload["size"]
    attachment.kind_code = payload["kind_code"]
    if payload["source_download_url"]:
        attachment.source_download_url = payload["source_download_url"]
    attachment.source_payload = payload["source_payload"]
    attachment.status = _status_after_download(attachment.status) if preserve_analyzed_status else status
    session.flush()
    return attachment


def upsert_attachments(bid_no: str, bid_ord: str, attachments: list[dict]) -> Optional[int]:
    if not is_enabled():
        return None
    with session_scope() as session:
        notice = upsert_notice_in_session(
            session,
            {"bidNtceNo": bid_no, "bidNtceOrd": bid_ord, "status": "attachments_ready"},
        )
        count = 0
        for item in attachments:
            get_or_create_attachment(session, notice, item, status="discovered")
            count += 1
        return count


def attachment_id(bid_no: str, bid_ord: str, selected: dict) -> Optional[int]:
    if not is_enabled():
        return None
    with session_scope() as session:
        notice = upsert_notice_in_session(session, {"bidNtceNo": bid_no, "bidNtceOrd": bid_ord})
        attachment = get_or_create_attachment(
            session,
            notice,
            selected,
            status="downloaded",
            preserve_analyzed_status=True,
        )
        return int(attachment.id)


def _upsert_attachment_file(
    session: Session,
    attachment_id_value: int,
    *,
    file_role: str,
    storage_path: str,
    size: int = 0,
    status: str = "downloaded",
    error: str = "",
) -> AttachmentFile:
    existing = session.execute(
        select(AttachmentFile).where(
            AttachmentFile.attachment_id == attachment_id_value,
            AttachmentFile.file_role == file_role,
            AttachmentFile.storage_path == storage_path,
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = AttachmentFile(
            attachment_id=attachment_id_value,
            file_role=file_role,
            storage_path=storage_path,
            size=size,
            status=status,
            error=error or None,
        )
        session.add(existing)
    else:
        existing.size = size
        existing.status = status
        existing.error = error or None
    session.flush()
    return existing


def record_downloads(bid_no: str, bid_ord: str, downloads: list[dict]) -> Optional[int]:
    if not is_enabled():
        return None
    with session_scope() as session:
        count = 0
        for item in downloads:
            selected = item.get("selected") or {}
            notice = upsert_notice_in_session(session, {"bidNtceNo": bid_no, "bidNtceOrd": bid_ord})
            attachment = get_or_create_attachment(
                session,
                notice,
                selected,
                status="downloaded",
                preserve_analyzed_status=True,
            )
            file_path = Path(item.get("filePath") or item.get("pdfPath") or "")
            size = file_path.stat().st_size if file_path.exists() else _as_int(selected.get("fileSz"))
            _upsert_attachment_file(
                session,
                int(attachment.id),
                file_role="original",
                storage_path=str(file_path),
                size=size,
                status="downloaded",
            )
            if notice.status != "analysis_ready":
                notice.status = "files_ready"
            count += 1
        return count
