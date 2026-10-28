"""transfer jobs

Revision ID: b8e1f6a3c959
Revises: a7d0e5f2b848
Create Date: 2026-10-26 18:26:20.796088

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b8e1f6a3c959"
down_revision = "a7d0e5f2b848"
branch_labels = None
depends_on = None

# Created and dropped explicitly, like the other types, and referenced with
# `create_type=False` so the table definitions do not emit CREATE TYPE again. The last two
# already exist and are only referenced.
TRANSFER_STATUS = postgresql.ENUM(
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
    name="transfer_status",
    create_type=False,
)
CONFIDENCE_BAND = postgresql.ENUM(
    "high", "medium", "low", name="confidence_band", create_type=False
)
EXECUTION_STATUS = postgresql.ENUM(name="execution_status", create_type=False)
RELEVANCE_GRADE = postgresql.ENUM(name="relevance_grade", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    TRANSFER_STATUS.create(bind, checkfirst=True)
    CONFIDENCE_BAND.create(bind, checkfirst=True)

    op.create_table(
        "transfer_jobs",
        sa.Column("qa_set_id", sa.UUID(), nullable=False),
        sa.Column("source_configuration_id", sa.UUID(), nullable=True),
        sa.Column("target_configuration_id", sa.UUID(), nullable=False),
        sa.Column("embedding_profile_id", sa.UUID(), nullable=True),
        sa.Column("workflow_id", sa.Text(), nullable=True),
        sa.Column("status", TRANSFER_STATUS, server_default="pending", nullable=False),
        sa.Column(
            "signal_weights",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "confidence_thresholds",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "progress",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("recall_ceiling", sa.Double(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
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
            ["embedding_profile_id"],
            ["embedding_profiles.id"],
            name=op.f("fk_transfer_jobs_embedding_profile_id_embedding_profiles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["qa_set_id"],
            ["qa_sets.id"],
            name=op.f("fk_transfer_jobs_qa_set_id_qa_sets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_configuration_id"],
            ["chunking_configurations.id"],
            name=op.f(
                "fk_transfer_jobs_source_configuration_id_chunking_configurations"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_configuration_id"],
            ["chunking_configurations.id"],
            name=op.f(
                "fk_transfer_jobs_target_configuration_id_chunking_configurations"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transfer_jobs")),
        sa.UniqueConstraint("workflow_id", name=op.f("uq_transfer_jobs_workflow_id")),
    )
    op.create_index(
        op.f("ix_transfer_jobs_embedding_profile_id"),
        "transfer_jobs",
        ["embedding_profile_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transfer_jobs_qa_set_id"), "transfer_jobs", ["qa_set_id"], unique=False
    )
    op.create_index(
        op.f("ix_transfer_jobs_source_configuration_id"),
        "transfer_jobs",
        ["source_configuration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transfer_jobs_target_configuration_id"),
        "transfer_jobs",
        ["target_configuration_id"],
        unique=False,
    )
    op.create_table(
        "transfer_questions",
        sa.Column("transfer_job_id", sa.UUID(), nullable=False),
        sa.Column("question_id", sa.UUID(), nullable=False),
        sa.Column("status", EXECUTION_STATUS, server_default="pending", nullable=False),
        sa.Column("candidate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_transfer_questions_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["transfer_job_id"],
            ["transfer_jobs.id"],
            name=op.f("fk_transfer_questions_transfer_job_id_transfer_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transfer_questions")),
        sa.UniqueConstraint(
            "transfer_job_id",
            "question_id",
            name=op.f("uq_transfer_questions_transfer_job_id_question_id"),
        ),
    )
    op.create_index(
        op.f("ix_transfer_questions_question_id"),
        "transfer_questions",
        ["question_id"],
        unique=False,
    )
    op.create_table(
        "transfer_candidates",
        sa.Column("transfer_job_id", sa.UUID(), nullable=False),
        sa.Column("question_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("combined_score", sa.Double(), nullable=False),
        sa.Column("semantic_score", sa.Double(), nullable=True),
        sa.Column("lexical_score", sa.Double(), nullable=True),
        sa.Column("positional_score", sa.Double(), nullable=True),
        sa.Column("confidence", CONFIDENCE_BAND, nullable=False),
        sa.Column(
            "preselected", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("suggested_relevance", RELEVANCE_GRADE, nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
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
            ["chunk_id"],
            ["chunks.id"],
            name=op.f("fk_transfer_candidates_chunk_id_chunks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_transfer_candidates_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["transfer_job_id"],
            ["transfer_jobs.id"],
            name=op.f("fk_transfer_candidates_transfer_job_id_transfer_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transfer_candidates")),
        sa.UniqueConstraint(
            "transfer_job_id",
            "question_id",
            "chunk_id",
            name=op.f("uq_transfer_candidates_transfer_job_id_question_id_chunk_id"),
        ),
    )
    op.create_index(
        op.f("ix_transfer_candidates_chunk_id"),
        "transfer_candidates",
        ["chunk_id"],
        unique=False,
    )
    op.create_index(
        "ix_transfer_candidates_job_question_rank",
        "transfer_candidates",
        ["transfer_job_id", "question_id", "rank"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transfer_candidates_job_question_rank", table_name="transfer_candidates"
    )
    op.drop_index(
        op.f("ix_transfer_candidates_chunk_id"), table_name="transfer_candidates"
    )
    op.drop_table("transfer_candidates")
    op.drop_index(
        op.f("ix_transfer_questions_question_id"), table_name="transfer_questions"
    )
    op.drop_table("transfer_questions")
    op.drop_index(
        op.f("ix_transfer_jobs_target_configuration_id"), table_name="transfer_jobs"
    )
    op.drop_index(
        op.f("ix_transfer_jobs_source_configuration_id"), table_name="transfer_jobs"
    )
    op.drop_index(op.f("ix_transfer_jobs_qa_set_id"), table_name="transfer_jobs")
    op.drop_index(
        op.f("ix_transfer_jobs_embedding_profile_id"), table_name="transfer_jobs"
    )
    op.drop_table("transfer_jobs")

    bind = op.get_bind()
    CONFIDENCE_BAND.drop(bind, checkfirst=True)
    TRANSFER_STATUS.drop(bind, checkfirst=True)
