"""evidence links

Revision ID: f6c9d4e1a737
Revises: e5b8c3d0f626
Create Date: 2026-10-26 16:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "f6c9d4e1a737"
down_revision = "e5b8c3d0f626"
branch_labels = None
depends_on = None

# Created and dropped explicitly, like the other types, and referenced with
# `create_type=False` so the table definitions do not emit CREATE TYPE again.
EVIDENCE_LINK_STATUS = postgresql.ENUM(
    "to_review",
    "confirmed",
    "not_found",
    name="evidence_link_status",
    create_type=False,
)
RELEVANCE_GRADE = postgresql.ENUM(
    "sufficient",
    "supporting",
    name="relevance_grade",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    EVIDENCE_LINK_STATUS.create(bind, checkfirst=True)
    RELEVANCE_GRADE.create(bind, checkfirst=True)

    op.add_column(
        "questions", sa.Column("replaced_by_question_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_questions_replaced_by_question_id_questions"),
        "questions",
        "questions",
        ["replaced_by_question_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_questions_replaced_by_question_id"),
        "questions",
        ["replaced_by_question_id"],
        unique=False,
    )

    op.create_table(
        "evidence_links",
        sa.Column("question_id", sa.UUID(), nullable=False),
        sa.Column("chunking_configuration_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            EVIDENCE_LINK_STATUS,
            server_default="to_review",
            nullable=False,
        ),
        sa.Column("confirmed_by", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["chunking_configuration_id"],
            ["chunking_configurations.id"],
            name=op.f(
                "fk_evidence_links_chunking_configuration_id_chunking_configurations"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_evidence_links_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_links")),
        sa.UniqueConstraint(
            "question_id",
            "chunking_configuration_id",
            name=op.f("uq_evidence_links_question_id_chunking_configuration_id"),
        ),
    )
    op.create_index(
        op.f("ix_evidence_links_question_id"),
        "evidence_links",
        ["question_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidence_links_chunking_configuration_id"),
        "evidence_links",
        ["chunking_configuration_id"],
        unique=False,
    )

    op.create_table(
        "evidence_link_chunks",
        sa.Column("evidence_link_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("relevance", RELEVANCE_GRADE, nullable=False),
        sa.Column("graded_relevance", sa.SmallInteger(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.id"],
            name=op.f("fk_evidence_link_chunks_chunk_id_chunks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_link_id"],
            ["evidence_links.id"],
            name=op.f("fk_evidence_link_chunks_evidence_link_id_evidence_links"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_link_chunks")),
        sa.UniqueConstraint(
            "evidence_link_id",
            "chunk_id",
            name=op.f("uq_evidence_link_chunks_evidence_link_id_chunk_id"),
        ),
    )
    op.create_index(
        op.f("ix_evidence_link_chunks_evidence_link_id"),
        "evidence_link_chunks",
        ["evidence_link_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidence_link_chunks_chunk_id"),
        "evidence_link_chunks",
        ["chunk_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_evidence_link_chunks_chunk_id"), table_name="evidence_link_chunks"
    )
    op.drop_index(
        op.f("ix_evidence_link_chunks_evidence_link_id"),
        table_name="evidence_link_chunks",
    )
    op.drop_table("evidence_link_chunks")
    op.drop_index(
        op.f("ix_evidence_links_chunking_configuration_id"),
        table_name="evidence_links",
    )
    op.drop_index(op.f("ix_evidence_links_question_id"), table_name="evidence_links")
    op.drop_table("evidence_links")

    op.drop_index(op.f("ix_questions_replaced_by_question_id"), table_name="questions")
    op.drop_constraint(
        op.f("fk_questions_replaced_by_question_id_questions"),
        "questions",
        type_="foreignkey",
    )
    op.drop_column("questions", "replaced_by_question_id")

    bind = op.get_bind()
    RELEVANCE_GRADE.drop(bind, checkfirst=True)
    EVIDENCE_LINK_STATUS.drop(bind, checkfirst=True)
