from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class NoticeAttachment(Base):
    __tablename__ = "notice_attachments"
    __table_args__ = (
        UniqueConstraint("notice_id", "attachment_key", name="uq_notice_attachments_notice_key"),
        Index("idx_notice_attachments_notice", "notice_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    notice_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("notices.id", ondelete="CASCADE"), nullable=False)
    attachment_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_file_name: Mapped[str] = mapped_column(Text, nullable=False)
    extension: Mapped[Optional[str]] = mapped_column(Text)
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    kind_code: Mapped[Optional[str]] = mapped_column(Text)
    source_download_url: Mapped[Optional[str]] = mapped_column(Text)
    source_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="discovered")
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    notice = relationship("Notice", back_populates="attachments")
    files = relationship("AttachmentFile", back_populates="attachment", cascade="all, delete-orphan")
    extractions = relationship("DocumentExtraction", back_populates="attachment", cascade="all, delete-orphan")
    analyses = relationship("DocumentAnalysis", back_populates="attachment", cascade="all, delete-orphan")


class AttachmentFile(Base):
    __tablename__ = "attachment_files"
    __table_args__ = (
        UniqueConstraint("attachment_id", "file_role", "storage_path", name="uq_attachment_files_role_path"),
        Index("idx_attachment_files_attachment", "attachment_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    attachment_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("notice_attachments.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_role: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(Text)
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    checksum: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="downloaded")
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    attachment = relationship("NoticeAttachment", back_populates="files")
