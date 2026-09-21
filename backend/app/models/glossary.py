from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.paper import Paper
    from app.models.user import User


class GlossaryScope(enum.StrEnum):
    USER_GLOBAL = "USER_GLOBAL"
    PAPER = "PAPER"


class GlossaryTerm(Base):
    __tablename__ = "glossary_terms"
    __table_args__ = (
        CheckConstraint(
            "(scope = 'USER_GLOBAL' AND paper_id IS NULL) OR "
            "(scope = 'PAPER' AND paper_id IS NOT NULL)",
            name="ck_glossary_scope_paper",
        ),
        Index("ix_glossary_user_scope_enabled", "user_id", "scope", "enabled"),
        Index("ix_glossary_paper_enabled", "paper_id", "enabled"),
        Index(
            "uq_glossary_global_term",
            "user_id",
            "source_language",
            "target_language",
            "source_term",
            unique=True,
            postgresql_where=text("paper_id IS NULL"),
        ),
        Index(
            "uq_glossary_paper_term",
            "paper_id",
            "source_language",
            "target_language",
            "source_term",
            unique=True,
            postgresql_where=text("paper_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    paper_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("papers.id", ondelete="CASCADE"),
    )
    source_term: Mapped[str] = mapped_column(Text)
    target_term: Mapped[str] = mapped_column(Text)
    source_language: Mapped[str] = mapped_column(String(32))
    target_language: Mapped[str] = mapped_column(String(32))
    scope: Mapped[str] = mapped_column(String(32))
    case_sensitive: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="glossary_terms")
    paper: Mapped[Paper | None] = relationship(back_populates="glossary_terms")
