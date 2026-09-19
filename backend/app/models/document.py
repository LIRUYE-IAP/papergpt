from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.paper import Paper


class BlockType(enum.StrEnum):
    TITLE = "TITLE"
    AUTHOR = "AUTHOR"
    AFFILIATION = "AFFILIATION"
    ABSTRACT = "ABSTRACT"
    KEYWORDS = "KEYWORDS"
    HEADING_1 = "HEADING_1"
    HEADING_2 = "HEADING_2"
    HEADING_3 = "HEADING_3"
    PARAGRAPH = "PARAGRAPH"
    FIGURE = "FIGURE"
    FIGURE_CAPTION = "FIGURE_CAPTION"
    TABLE = "TABLE"
    TABLE_CAPTION = "TABLE_CAPTION"
    EQUATION = "EQUATION"
    FOOTNOTE = "FOOTNOTE"
    REFERENCE = "REFERENCE"
    HEADER = "HEADER"
    FOOTER = "FOOTER"
    PAGE_NUMBER = "PAGE_NUMBER"


block_type_enum = Enum(
    BlockType,
    name="block_type",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    length=32,
)


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("paper_id", "order_index", name="uq_sections_paper_order"),
        Index("ix_sections_paper_parent", "paper_id", "parent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sections.id", ondelete="CASCADE"),
    )
    title_original: Mapped[str] = mapped_column(Text)
    title_zh: Mapped[str | None] = mapped_column(Text)
    level: Mapped[int] = mapped_column(Integer)
    order_index: Mapped[int] = mapped_column(Integer)
    start_page: Mapped[int] = mapped_column(Integer)
    end_page: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    paper: Mapped[Paper] = relationship(back_populates="sections")
    parent: Mapped[Section | None] = relationship(
        back_populates="children",
        remote_side="Section.id",
    )
    children: Mapped[list[Section]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
        single_parent=True,
    )
    blocks: Mapped[list[Block]] = relationship(back_populates="section")


class Block(Base):
    __tablename__ = "blocks"
    __table_args__ = (
        UniqueConstraint("paper_id", "reading_order", name="uq_blocks_paper_order"),
        Index("ix_blocks_paper_page_order", "paper_id", "page_number", "reading_order"),
        Index("ix_blocks_paper_type", "paper_id", "block_type"),
        Index("ix_blocks_section", "section_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sections.id", ondelete="SET NULL"),
    )
    page_number: Mapped[int] = mapped_column(Integer)
    block_type: Mapped[BlockType] = mapped_column(block_type_enum)
    original_text: Mapped[str] = mapped_column(Text)
    reading_order: Mapped[int] = mapped_column(Integer)
    bbox: Mapped[dict[str, Any]] = mapped_column(JSONB)
    column_index: Mapped[int | None] = mapped_column(Integer)
    parent_block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("blocks.id", ondelete="SET NULL"),
    )
    block_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    is_translatable: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    paper: Mapped[Paper] = relationship(back_populates="blocks")
    section: Mapped[Section | None] = relationship(back_populates="blocks")
    parent_block: Mapped[Block | None] = relationship(
        back_populates="child_blocks",
        remote_side="Block.id",
    )
    child_blocks: Mapped[list[Block]] = relationship(back_populates="parent_block")
