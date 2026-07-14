from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import is_enabled, session_scope
from app.models import Notice


def _as_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _notice_identity(payload: dict) -> tuple[str, str]:
    bid_no = _as_text(payload.get("bidNtceNo") or payload.get("bid_ntce_no") or payload.get("number"))
    bid_ord = _as_text(payload.get("bidNtceOrd") or payload.get("bid_ntce_ord"), "000")
    return bid_no, bid_ord


def _notice_number(payload: dict, bid_no: str) -> str:
    return _as_text(payload.get("number") or payload.get("bidNtceFullNo") or bid_no)


def _incoming_has_public_payload(payload: dict) -> bool:
    return any(payload.get(key) for key in ("title", "bidNtceNm", "number"))


def _coalesce(existing: Optional[str], incoming: Any) -> Optional[str]:
    incoming_text = _as_text(incoming)
    return incoming_text or existing


def _budget(existing: int, incoming: Any) -> int:
    incoming_int = _as_int(incoming)
    return existing if incoming_int == 0 else incoming_int


def _status(existing: str, incoming: Any) -> str:
    incoming_text = _as_text(incoming, "listed")
    if existing == "analysis_ready":
        return existing
    if incoming_text == "listed":
        return existing
    return incoming_text


def upsert_notice_in_session(session: Session, payload: dict) -> Notice:
    bid_no, bid_ord = _notice_identity(payload)
    notice = session.execute(
        select(Notice).where(Notice.bid_ntce_no == bid_no, Notice.bid_ntce_ord == bid_ord)
    ).scalar_one_or_none()
    if notice is None:
        notice = Notice(
            bid_ntce_no=bid_no,
            bid_ntce_ord=bid_ord,
            notice_number=_notice_number(payload, bid_no),
            title=_as_text(payload.get("title") or payload.get("bidNtceNm")),
            agency=_as_text(payload.get("agency") or payload.get("ntceInsttNm")),
            demand_agency=_as_text(payload.get("demandAgency") or payload.get("dmndInsttNm")),
            region=_as_text(payload.get("region")),
            industry=_as_text(payload.get("industry")),
            method=_as_text(payload.get("method") or payload.get("bidMthdNm")),
            category=_as_text(payload.get("category")),
            qualification_source=_as_text(payload.get("qualificationSource")),
            budget=_as_int(payload.get("budget")),
            score=_as_int(payload.get("score") or payload.get("_score")),
            grade=_as_text(payload.get("grade") or payload.get("_grade")),
            deep_link=_as_text(payload.get("deepLink")),
            status=_as_text(payload.get("status"), "listed"),
            raw_payload=payload if _incoming_has_public_payload(payload) else {},
        )
        session.add(notice)
        session.flush()
        return notice

    notice.notice_number = _coalesce(notice.notice_number, _notice_number(payload, bid_no))
    notice.title = _coalesce(notice.title, payload.get("title") or payload.get("bidNtceNm"))
    notice.agency = _coalesce(notice.agency, payload.get("agency") or payload.get("ntceInsttNm"))
    notice.demand_agency = _coalesce(notice.demand_agency, payload.get("demandAgency") or payload.get("dmndInsttNm"))
    notice.region = _coalesce(notice.region, payload.get("region"))
    notice.industry = _coalesce(notice.industry, payload.get("industry"))
    notice.method = _coalesce(notice.method, payload.get("method") or payload.get("bidMthdNm"))
    notice.category = _coalesce(notice.category, payload.get("category"))
    notice.qualification_source = _coalesce(notice.qualification_source, payload.get("qualificationSource"))
    notice.budget = _budget(notice.budget or 0, payload.get("budget"))
    notice.score = _budget(notice.score or 0, payload.get("score") or payload.get("_score"))
    notice.grade = _coalesce(notice.grade, payload.get("grade") or payload.get("_grade"))
    notice.deep_link = _coalesce(notice.deep_link, payload.get("deepLink"))
    notice.status = _status(notice.status, payload.get("status"))
    if _incoming_has_public_payload(payload):
        notice.raw_payload = payload
    session.flush()
    return notice


def upsert_notice(payload: dict) -> Optional[int]:
    if not is_enabled():
        return None
    with session_scope() as session:
        notice = upsert_notice_in_session(session, payload)
        return int(notice.id)


def persist_dashboard_payload(payload: dict) -> Optional[int]:
    if not is_enabled():
        return None
    with session_scope() as session:
        count = 0
        for notice_payload in payload.get("notices", []):
            if notice_payload.get("bidNtceNo") or notice_payload.get("number"):
                upsert_notice_in_session(session, notice_payload)
                count += 1
        return count


def load_dashboard_payload() -> Optional[dict]:
    if not is_enabled():
        return None
    with session_scope() as session:
        rows = session.execute(select(Notice).order_by(Notice.score.desc(), Notice.updated_at.desc())).scalars().all()
        notices = [
            row.raw_payload
            for row in rows
            if isinstance(row.raw_payload, dict)
            and any(row.raw_payload.get(key) for key in ("title", "bidNtceNm", "number"))
        ]
        if not notices:
            return None
        return {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "qualified": len(notices),
                "disqualified": 0,
                "keywords": sorted({kw for notice in notices for kw in (notice.get("keywords") or [])}),
            },
            "notices": notices,
        }
