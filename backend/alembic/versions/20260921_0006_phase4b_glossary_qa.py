"""Add Phase 4B glossary terms and deterministic QA results.

Revision ID: 20260921_0006
Revises: 20260920_0005
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260921_0006"
down_revision: str | None = "20260920_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "glossary_terms",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("paper_id", sa.UUID(), nullable=True),
        sa.Column("source_term", sa.Text(), nullable=False),
        sa.Column("target_term", sa.Text(), nullable=False),
        sa.Column("source_language", sa.String(length=32), nullable=False),
        sa.Column("target_language", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column(
            "case_sensitive",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "enabled",
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
        sa.CheckConstraint(
            "(scope = 'USER_GLOBAL' AND paper_id IS NULL) OR "
            "(scope = 'PAPER' AND paper_id IS NOT NULL)",
            name="ck_glossary_scope_paper",
        ),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_glossary_user_scope_enabled",
        "glossary_terms",
        ["user_id", "scope", "enabled"],
    )
    op.create_index(
        "ix_glossary_paper_enabled",
        "glossary_terms",
        ["paper_id", "enabled"],
    )
    op.create_index(
        "uq_glossary_global_term",
        "glossary_terms",
        ["user_id", "source_language", "target_language", "source_term"],
        unique=True,
        postgresql_where=sa.text("paper_id IS NULL"),
    )
    op.create_index(
        "uq_glossary_paper_term",
        "glossary_terms",
        ["paper_id", "source_language", "target_language", "source_term"],
        unique=True,
        postgresql_where=sa.text("paper_id IS NOT NULL"),
    )

    op.create_table(
        "translation_qa_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("translation_id", sa.UUID(), nullable=False),
        sa.Column("check_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["translation_id"],
            ["translations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "translation_id",
            "check_type",
            name="uq_translation_qa_translation_check",
        ),
    )
    op.create_index(
        "ix_translation_qa_translation",
        "translation_qa_results",
        ["translation_id"],
    )
    op.create_index(
        "ix_translation_qa_status",
        "translation_qa_results",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_translation_qa_status", table_name="translation_qa_results")
    op.drop_index(
        "ix_translation_qa_translation",
        table_name="translation_qa_results",
    )
    op.drop_table("translation_qa_results")
    op.drop_index("uq_glossary_paper_term", table_name="glossary_terms")
    op.drop_index("uq_glossary_global_term", table_name="glossary_terms")
    op.drop_index("ix_glossary_paper_enabled", table_name="glossary_terms")
    op.drop_index("ix_glossary_user_scope_enabled", table_name="glossary_terms")
    op.drop_table("glossary_terms")
