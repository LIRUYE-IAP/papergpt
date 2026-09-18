"""Add Phase 1 paper upload fields and status defaults.

Revision ID: 20260918_0002
Revises: 20260918_0001
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_0002"
down_revision: str | None = "20260918_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("papers", sa.Column("file_size", sa.BigInteger(), nullable=True))
    op.execute("UPDATE papers SET file_size = 0 WHERE file_size IS NULL")
    op.alter_column("papers", "file_size", nullable=False)

    op.execute(
        "UPDATE papers SET parse_status = 'NOT_STARTED' "
        "WHERE parse_status = 'pending'"
    )
    op.execute(
        "UPDATE papers SET translation_status = 'NOT_STARTED' "
        "WHERE translation_status = 'pending'"
    )
    op.execute("UPDATE papers SET qa_status = 'PENDING' WHERE qa_status = 'pending'")
    op.alter_column(
        "papers",
        "parse_status",
        existing_type=sa.String(length=32),
        server_default="NOT_STARTED",
        existing_nullable=False,
    )
    op.alter_column(
        "papers",
        "translation_status",
        existing_type=sa.String(length=32),
        server_default="NOT_STARTED",
        existing_nullable=False,
    )
    op.alter_column(
        "papers",
        "qa_status",
        existing_type=sa.String(length=32),
        server_default="PENDING",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.execute(
        "UPDATE papers SET parse_status = 'pending' "
        "WHERE parse_status = 'NOT_STARTED'"
    )
    op.execute(
        "UPDATE papers SET translation_status = 'pending' "
        "WHERE translation_status = 'NOT_STARTED'"
    )
    op.execute("UPDATE papers SET qa_status = 'pending' WHERE qa_status = 'PENDING'")
    op.alter_column(
        "papers",
        "qa_status",
        existing_type=sa.String(length=32),
        server_default="pending",
        existing_nullable=False,
    )
    op.alter_column(
        "papers",
        "translation_status",
        existing_type=sa.String(length=32),
        server_default="pending",
        existing_nullable=False,
    )
    op.alter_column(
        "papers",
        "parse_status",
        existing_type=sa.String(length=32),
        server_default="pending",
        existing_nullable=False,
    )
    op.drop_column("papers", "file_size")
