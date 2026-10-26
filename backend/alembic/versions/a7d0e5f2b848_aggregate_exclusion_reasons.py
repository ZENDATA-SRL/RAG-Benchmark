"""aggregate exclusion reasons

Revision ID: a7d0e5f2b848
Revises: f6c9d4e1a737
Create Date: 2026-10-26 18:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "a7d0e5f2b848"
down_revision = "f6c9d4e1a737"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "metric_aggregates",
        sa.Column(
            "excluded_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("metric_aggregates", "excluded_reasons")
