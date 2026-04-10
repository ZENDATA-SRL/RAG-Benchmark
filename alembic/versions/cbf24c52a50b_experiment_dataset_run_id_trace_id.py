"""experiment dataset_run_id trace_id

Revision ID: cbf24c52a50b
Revises: 4ea51c3a83a6
Create Date: 2026-04-09 18:27:05.026217

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = 'cbf24c52a50b'
down_revision = '4ea51c3a83a6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "experiments",
        sa.Column("dataset_run_id", sa.String(), nullable=True),
    )
    op.add_column(
        "experiments",
        sa.Column("trace_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("experiments", "trace_id")
    op.drop_column("experiments", "dataset_run_id")

