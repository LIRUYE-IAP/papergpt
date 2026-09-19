"""Add Phase 2 document sections and blocks.

Revision ID: 20260918_0003
Revises: 20260918_0002
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260918_0003"
down_revision: str | None = "20260918_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

block_type = sa.Enum(
    "TITLE",
    "AUTHOR",
    "AFFILIATION",
    "ABSTRACT",
    "KEYWORDS",
    "HEADING_1",
    "HEADING_2",
    "HEADING_3",
    "PARAGRAPH",
    "FIGURE",
    "FIGURE_CAPTION",
    "TABLE",
    "TABLE_CAPTION",
    "EQUATION",
    "FOOTNOTE",
    "REFERENCE",
    "HEADER",
    "FOOTER",
    "PAGE_NUMBER",
    name="block_type",
    native_enum=False,
    create_constraint=True,
    length=32,
)


def upgrade() -> None:
    op.create_table(
        "sections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("paper_id", sa.UUID(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("title_original", sa.Text(), nullable=False),
        sa.Column("title_zh", sa.Text(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("start_page", sa.Integer(), nullable=False),
        sa.Column("end_page", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_id", "order_index", name="uq_sections_paper_order"),
    )
    op.create_index(
        "ix_sections_paper_parent", "sections", ["paper_id", "parent_id"]
    )

    op.create_table(
        "blocks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("paper_id", sa.UUID(), nullable=False),
        sa.Column("section_id", sa.UUID(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("block_type", block_type, nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("reading_order", sa.Integer(), nullable=False),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("column_index", sa.Integer(), nullable=True),
        sa.Column("parent_block_id", sa.UUID(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "is_translatable",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["section_id"], ["sections.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["parent_block_id"], ["blocks.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_id", "reading_order", name="uq_blocks_paper_order"),
    )
    op.create_index("ix_blocks_section", "blocks", ["section_id"])
    op.create_index(
        "ix_blocks_paper_page_order",
        "blocks",
        ["paper_id", "page_number", "reading_order"],
    )
    op.create_index("ix_blocks_paper_type", "blocks", ["paper_id", "block_type"])


def downgrade() -> None:
    op.drop_index("ix_blocks_paper_type", table_name="blocks")
    op.drop_index("ix_blocks_paper_page_order", table_name="blocks")
    op.drop_index("ix_blocks_section", table_name="blocks")
    op.drop_table("blocks")
    op.drop_index("ix_sections_paper_parent", table_name="sections")
    op.drop_table("sections")
