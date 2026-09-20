"""Preserve translated Blocks during parse reconciliation.

Revision ID: 20260920_0005
Revises: 20260919_0004
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_0005"
down_revision: str | None = "20260919_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "blocks",
        sa.Column(
            "is_stale",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.drop_constraint("uq_blocks_paper_order", "blocks", type_="unique")
    op.create_index(
        "uq_blocks_paper_active_order",
        "blocks",
        ["paper_id", "reading_order"],
        unique=True,
        postgresql_where=sa.text("is_stale = false"),
    )
    op.create_index(
        "ix_blocks_paper_stale",
        "blocks",
        ["paper_id", "is_stale"],
    )


def downgrade() -> None:
    op.drop_index("ix_blocks_paper_stale", table_name="blocks")
    op.drop_index("uq_blocks_paper_active_order", table_name="blocks")
    op.execute(
        sa.text(
            """
            WITH ranked_stale AS (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY paper_id
                        ORDER BY created_at, id
                    ) AS stale_order
                FROM blocks
                WHERE is_stale = true
            )
            UPDATE blocks AS block
            SET reading_order = -ranked_stale.stale_order
            FROM ranked_stale
            WHERE block.id = ranked_stale.id
            """
        )
    )
    op.drop_column("blocks", "is_stale")
    op.create_unique_constraint(
        "uq_blocks_paper_order",
        "blocks",
        ["paper_id", "reading_order"],
    )
