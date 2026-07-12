from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Notice(Base):
    __tablename__ = "notices"
    __table_args__ = (
        UniqueConstraint("bid_ntce_no", "bid_ntce_ord", name="uq_notices_bid_ntce"),
        Index("idx_notices_score", "score"),
        Index("idx_notices_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    bid_ntce_no: Mapped[str] = mapped_column(Text, nullable=False)
    bid_ntce_ord: Mapped[str] = mapped_column(Text, nullable=False, default="000")
    notice_number: Mapped[Optional[str]] = mapped_column(Text)
    title: Mapped[Optional[str]] = mapped_column(Text)
    agency: Mapped[Optional[str]] = mapped_column(Text)
    demand_agency: Mapped[Optional[str]] = mapped_column(Text)
    region: Mapped[Optional[str]] = mapped_column(Text)
    industry: Mapped[Optional[str]] = mapped_column(Text)
    method: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(Text)
    qualification_source: Mapped[Optional[str]] = mapped_column(Text)
    budget: Mapped[int] = mapped_column(BigInteger, default=0)
    score: Mapped[int] = mapped_column(Integer, default=0)
    grade: Mapped[Optional[str]] = mapped_column(String)
    deep_link: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="listed")
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    attachments = relationship("NoticeAttachment", back_populates="notice", cascade="all, delete-orphan")
    analyses = relationship("NoticeAnalysis", back_populates="notice", cascade="all, delete-orphan")
    checklist_state = relationship(
        "ProposalChecklistState",
        back_populates="notice",
        cascade="all, delete-orphan",
        uselist=False,
    )
