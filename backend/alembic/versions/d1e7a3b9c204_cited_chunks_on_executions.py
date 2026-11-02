"""cited chunks on executions

Revision ID: d1e7a3b9c204
Revises: c9f2a7b4d16e
Create Date: 2026-10-29 10:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "d1e7a3b9c204"
down_revision = "c9f2a7b4d16e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "executions",
        sa.Column("cited_chunk_ids", postgresql.ARRAY(sa.UUID()), nullable=True),
    )
    # Never written: citations belong to the execution, and "in context" is not observed.
    op.drop_column("retrieval_hits", "in_context")
    op.drop_column("retrieval_hits", "cited")


def downgrade() -> None:
    op.add_column(
        "retrieval_hits",
        sa.Column(
            "cited", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.add_column(
        "retrieval_hits",
        sa.Column(
            "in_context", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.drop_column("executions", "cited_chunk_ids")
