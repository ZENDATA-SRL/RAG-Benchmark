"""materialization_runs.error

Revision ID: b1c4f7d2e803
Revises: a809ee42c9d0
Create Date: 2026-08-28 17:20:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b1c4f7d2e803'
down_revision = 'a809ee42c9d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Why a run needs its own error while the artefacts already have one: a cancelled run
    # leaves every chunk_result untouched, so without this column the UI would show a run
    # that is `failed` and no reason anywhere.
    op.add_column('materialization_runs', sa.Column('error', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('materialization_runs', 'error')
