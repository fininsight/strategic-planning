from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProposalChecklistState(Base):
    __tablename__ = "proposal_checklist_states"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    notice_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("notices.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    checks_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    notice = relationship("Notice", back_populates="checklist_state")
