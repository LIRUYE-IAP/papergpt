"""Create initial users and papers schema.

Revision ID: 20260918_0001
Revises:
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260918_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "papers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("title_zh", sa.Text(), nullable=True),
        sa.Column(
            "authors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("journal", sa.String(length=512), nullable=True),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("source_language", sa.String(length=32), nullable=True),
        sa.Column("target_language", sa.String(length=32), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("file_key", sa.String(length=1024), nullable=False),
        sa.Column("file_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "document_type", sa.String(length=32), server_default="pdf", nullable=False
        ),
        sa.Column(
            "parse_status", sa.String(length=32), server_default="pending", nullable=False
        ),
        sa.Column(
            "translation_status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "qa_status", sa.String(length=32), server_default="pending", nullable=False
        ),
        sa.Column("current_page", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "reading_progress",
            sa.Numeric(precision=5, scale=2),
            server_default="0",
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
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_key"),
    )
    op.create_index(op.f("ix_papers_doi"), "papers", ["doi"], unique=False)
    op.create_index(op.f("ix_papers_file_hash"), "papers", ["file_hash"], unique=False)
    op.create_index(op.f("ix_papers_user_id"), "papers", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_papers_user_id"), table_name="papers")
    op.drop_index(op.f("ix_papers_file_hash"), table_name="papers")
    op.drop_index(op.f("ix_papers_doi"), table_name="papers")
    op.drop_table("papers")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
