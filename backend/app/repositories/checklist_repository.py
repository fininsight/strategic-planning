from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import is_enabled, session_scope
from app.models import Notice, ProposalChecklistState


def normalize_checks_payload(checks: Any) -> dict[str, bool]:
    if not isinstance(checks, dict):
        return {}
    return {str(key): bool(value) for key, value in checks.items() if str(key).strip()}


def _notice_number(bid_no: str, bid_ord: str) -> str:
    return f"{bid_no}-{bid_ord}" if bid_ord else bid_no


def get_or_create_notice(session: Session, bid_no: str, bid_ord: str) -> Notice:
    notice = session.execute(
        select(Notice).where(Notice.bid_ntce_no == bid_no, Notice.bid_ntce_ord == bid_ord)
    ).scalar_one_or_none()
    if notice is not None:
        return notice

    notice = Notice(
        bid_ntce_no=bid_no,
        bid_ntce_ord=bid_ord,
        notice_number=_notice_number(bid_no, bid_ord),
        status="listed",
        raw_payload={},
    )
    session.add(notice)
    session.flush()
    return notice


def load_checklist_state(bid_no: str, bid_ord: str) -> dict | None:
    if not is_enabled():
        return None

    with session_scope() as session:
        notice = get_or_create_notice(session, bid_no, bid_ord)
        state = session.execute(
            select(ProposalChecklistState).where(ProposalChecklistState.notice_id == notice.id)
        ).scalar_one_or_none()
        if state is None:
            return None
        return {
            "checks": normalize_checks_payload(state.checks_payload),
            "updatedAt": state.updated_at.isoformat() if state.updated_at else "",
        }


def save_checklist_state(bid_no: str, bid_ord: str, checks: dict) -> dict | None:
    if not is_enabled():
        return None

    normalized_checks = normalize_checks_payload(checks)
    with session_scope() as session:
        notice = get_or_create_notice(session, bid_no, bid_ord)
        state = session.execute(
            select(ProposalChecklistState).where(ProposalChecklistState.notice_id == notice.id)
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if state is None:
            state = ProposalChecklistState(
                notice_id=notice.id,
                checks_payload=normalized_checks,
                updated_at=now,
            )
            session.add(state)
        else:
            state.checks_payload = normalized_checks
            state.updated_at = now
        session.flush()
        return {
            "checks": normalized_checks,
            "updatedAt": state.updated_at.isoformat() if state.updated_at else "",
        }
