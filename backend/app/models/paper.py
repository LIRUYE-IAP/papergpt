from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Block, Section
    from app.models.translation import Translation
    from app.models.user import User


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    filename: Mapped[str] = mapped_column(String(512))
    original_filename: Mapped[str] = mapped_column(String(512))

    title: Mapped[str | None] = mapped_column(Text)
    title_zh: Mapped[str | None] = mapped_column(Text)
    authors: Mapped[list[dict[str, Any] | str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    journal: Mapped[str | None] = mapped_column(String(512))
    doi: Mapped[str | None] = mapped_column(String(255), index=True)
    publication_year: Mapped[int | None] = mapped_column(Integer)

    source_language: Mapped[str | None] = mapped_column(String(32))
    target_language: Mapped[str | None] = mapped_column(String(32))
    page_count: Mapped[int | None] = mapped_column(Integer)
    file_size: Mapped[int] = mapped_column(BigInteger)

    file_key: Mapped[str] = mapped_column(String(1024), unique=True)
    file_hash: Mapped[str] = mapped_column(String(128), index=True)
    document_type: Mapped[str] = mapped_column(
        String(32), default="pdf", server_default="pdf"
    )

    parse_status: Mapped[str] = mapped_column(
        String(32), default="NOT_STARTED", server_default="NOT_STARTED"
    )
    translation_status: Mapped[str] = mapped_column(
        String(32), default="NOT_STARTED", server_default="NOT_STARTED"
    )
    qa_status: Mapped[str] = mapped_column(
        String(32), default="PENDING", server_default="PENDING"
    )

    current_page: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reading_progress: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0"), server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="papers")
    sections: Mapped[list[Section]] = relationship(
        back_populates="paper",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    blocks: Mapped[list[Block]] = relationship(
        back_populates="paper",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    translations: Mapped[list[Translation]] = relationship(
        back_populates="paper",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
