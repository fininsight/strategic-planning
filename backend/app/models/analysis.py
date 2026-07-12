from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DocumentExtraction(Base):
    __tablename__ = "document_extractions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    attachment_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("notice_attachments.id", ondelete="CASCADE"),
        nullable=False,
    )
    text_storage_path: Mapped[Optional[str]] = mapped_column(Text)
    text_length: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    extraction_method: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text)
    extracted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    attachment = relationship("NoticeAttachment", back_populates="extractions")


class DocumentAnalysis(Base):
    __tablename__ = "document_analyses"
    __table_args__ = (
        UniqueConstraint("attachment_id", "analysis_version", "analysis_type", name="uq_document_analyses_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    attachment_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("notice_attachments.id", ondelete="CASCADE"),
        nullable=False,
    )
    analysis_version: Mapped[int] = mapped_column(Integer, nullable=False)
    analysis_type: Mapped[str] = mapped_column(Text, nullable=False, default="rule")
    analysis_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text)
    analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    attachment = relationship("NoticeAttachment", back_populates="analyses")


class NoticeAnalysis(Base):
    __tablename__ = "notice_analyses"
    __table_args__ = (UniqueConstraint("notice_id", "analysis_version", name="uq_notice_analyses_version"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    notice_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("notices.id", ondelete="CASCADE"), nullable=False)
    analysis_version: Mapped[int] = mapped_column(Integer, nullable=False)
    summary_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    proposal_sheets_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    combined_text_storage_path: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text)
    analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    notice = relationship("Notice", back_populates="analyses")
