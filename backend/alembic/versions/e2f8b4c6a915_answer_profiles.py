"""answer profiles

Revision ID: e2f8b4c6a915
Revises: d1e7a3b9c204
Create Date: 2026-11-02 10:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e2f8b4c6a915"
down_revision = "d1e7a3b9c204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "answer_profiles",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("component_version_id", sa.UUID(), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("config_hash", sa.Text(), nullable=False),
        sa.Column("parent_profile_id", sa.UUID(), nullable=True),
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
            ["component_version_id"],
            ["component_versions.id"],
            name=op.f("fk_answer_profiles_component_version_id_component_versions"),
            ondelete="RESTRICT",
        ),
        # The derivation is informative: it must not keep a parent from being removed.
        sa.ForeignKeyConstraint(
            ["parent_profile_id"],
            ["answer_profiles.id"],
            name=op.f("fk_answer_profiles_parent_profile_id_answer_profiles"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answer_profiles")),
        sa.UniqueConstraint("config_hash", name=op.f("uq_answer_profiles_config_hash")),
    )
    op.create_index(
        op.f("ix_answer_profiles_component_version_id"),
        "answer_profiles",
        ["component_version_id"],
        unique=False,
    )
    # Every existing variant is a retrieval one with a NULL profile: no data to move.
    op.create_foreign_key(
        op.f("fk_variants_answer_profile_id_answer_profiles"),
        "variants",
        "answer_profiles",
        ["answer_profile_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_variants_answer_profile_id"),
        "variants",
        ["answer_profile_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_variants_answer_profile_id"), table_name="variants")
    op.drop_constraint(
        op.f("fk_variants_answer_profile_id_answer_profiles"),
        "variants",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_answer_profiles_component_version_id"), table_name="answer_profiles"
    )
    op.drop_table("answer_profiles")
