"""expected answers

Revision ID: e5b8c3d0f626
Revises: d4a7b2c9e515
Create Date: 2026-10-24 10:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e5b8c3d0f626"
down_revision = "d4a7b2c9e515"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expected_answers",
        sa.Column("question_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("rubric", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_expected_answers_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_expected_answers")),
    )
    op.create_index(
        op.f("ix_expected_answers_question_id"),
        "expected_answers",
        ["question_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_expected_answers_question_id"), table_name="expected_answers"
    )
    op.drop_table("expected_answers")
