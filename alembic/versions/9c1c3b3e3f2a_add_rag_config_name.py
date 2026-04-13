"""add rag_config name

Revision ID: 9c1c3b3e3f2a
Revises: 212a7020aeb0
Create Date: 2026-04-13

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "9c1c3b3e3f2a"
down_revision = "212a7020aeb0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add as non-null with a temporary default for existing rows,
    # then drop the default so new inserts must provide a name.
    op.add_column(
        "rag_configs",
        sa.Column("name", sa.String(), nullable=False, server_default="legacy"),
    )
    op.alter_column("rag_configs", "name", server_default=None)


def downgrade() -> None:
    op.drop_column("rag_configs", "name")

