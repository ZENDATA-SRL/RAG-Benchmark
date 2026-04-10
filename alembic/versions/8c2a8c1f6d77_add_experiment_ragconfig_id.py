"""add experiment ragconfig_id

Revision ID: 8c2a8c1f6d77
Revises: cbf24c52a50b
Create Date: 2026-04-10

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8c2a8c1f6d77"
down_revision = "cbf24c52a50b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "experiments",
        sa.Column("ragconfig_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_experiments_ragconfig_id_rag_configs",
        "experiments",
        "rag_configs",
        ["ragconfig_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_experiments_ragconfig_id_rag_configs",
        "experiments",
        type_="foreignkey",
    )
    op.drop_column("experiments", "ragconfig_id")

