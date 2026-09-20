from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Block
    from app.models.paper import Paper


class TranslationStatus(enum.StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


translation_status_enum = Enum(
    TranslationStatus,
    name="translation_status",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    length=32,
)


class Translation(Base):
    __tablename__ = "translations"
    __table_args__ = (
        UniqueConstraint(
            "block_id",
            "target_language",
            name="uq_translations_block_target_language",
        ),
        Index(
            "ix_translations_paper_target_status",
            "paper_id",
            "target_language",
            "status",
        ),
        Index("ix_translations_paper_block", "paper_id", "block_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
    )
    block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("blocks.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_language: Mapped[str] = mapped_column(String(32))
    target_language: Mapped[str] = mapped_column(String(32))
    original_text: Mapped[str] = mapped_column(Text)
    translated_text: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(255))
    status: Mapped[TranslationStatus] = mapped_column(
        translation_status_enum,
        default=TranslationStatus.PENDING,
        server_default=TranslationStatus.PENDING.value,
    )
    user_modified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    qa_status: Mapped[str] = mapped_column(
        String(32), default="PENDING", server_default="PENDING"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    translated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    paper: Mapped[Paper] = relationship(back_populates="translations")
    block: Mapped[Block] = relationship(back_populates="translations")
    versions: Mapped[list[TranslationVersion]] = relationship(
        back_populates="translation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TranslationVersion.version_number",
    )


class TranslationVersion(Base):
    __tablename__ = "translation_versions"
    __table_args__ = (
        UniqueConstraint(
            "translation_id",
            "version_number",
            name="uq_translation_versions_translation_number",
        ),
        Index("ix_translation_versions_translation", "translation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    translation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("translations.id", ondelete="CASCADE"),
        nullable=False,
    )
    translated_text: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(255))
    version_number: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reason: Mapped[str] = mapped_column(String(64))

    translation: Mapped[Translation] = relationship(back_populates="versions")
