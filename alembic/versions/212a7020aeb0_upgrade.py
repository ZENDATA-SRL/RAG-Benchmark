"""upgrade

Revision ID: 212a7020aeb0
Revises: 5f93f14eb925
Create Date: 2026-04-13 14:31:04.986530

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "212a7020aeb0"
down_revision = "5f93f14eb925"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "answer_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("answer_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["answer_id"], ["answers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("answer_id", "chunk_id"),
    )


def downgrade() -> None:
    op.drop_table("answer_chunks")

