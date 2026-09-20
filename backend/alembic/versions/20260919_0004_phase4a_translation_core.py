"""Add Phase 4A translations and translation versions.

Revision ID: 20260919_0004
Revises: 20260918_0003
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260919_0004"
down_revision: str | None = "20260918_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

translation_status = sa.Enum(
    "PENDING",
    "PROCESSING",
    "COMPLETED",
    "FAILED",
    name="translation_status",
    native_enum=False,
    create_constraint=True,
    length=32,
)


def upgrade() -> None:
    op.create_table(
        "translations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("paper_id", sa.UUID(), nullable=False),
        sa.Column("block_id", sa.UUID(), nullable=False),
        sa.Column("source_language", sa.String(length=32), nullable=False),
        sa.Column("target_language", sa.String(length=32), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("translated_text", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            translation_status,
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column(
            "user_modified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "qa_status",
            sa.String(length=32),
            server_default="PENDING",
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
        sa.Column("translated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["block_id"], ["blocks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "block_id",
            "target_language",
            name="uq_translations_block_target_language",
        ),
    )
    op.create_index(
        "ix_translations_paper_block",
        "translations",
        ["paper_id", "block_id"],
    )
    op.create_index(
        "ix_translations_paper_target_status",
        "translations",
        ["paper_id", "target_language", "status"],
    )

    op.create_table(
        "translation_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("translation_id", sa.UUID(), nullable=False),
        sa.Column("translated_text", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["translation_id"], ["translations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "translation_id",
            "version_number",
            name="uq_translation_versions_translation_number",
        ),
    )
    op.create_index(
        "ix_translation_versions_translation",
        "translation_versions",
        ["translation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_translation_versions_translation",
        table_name="translation_versions",
    )
    op.drop_table("translation_versions")
    op.drop_index("ix_translations_paper_target_status", table_name="translations")
    op.drop_index("ix_translations_paper_block", table_name="translations")
    op.drop_table("translations")
