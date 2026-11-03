"""generation jobs

Revision ID: 5974e723c3b1
Revises: e2f8b4c6a915
Create Date: 2026-11-02 18:27:04.962007

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "5974e723c3b1"
down_revision = "e2f8b4c6a915"
branch_labels = None
depends_on = None


# Created and dropped explicitly, like the other types, and referenced with
# `create_type=False` so the table definitions do not emit CREATE TYPE again. The last two
# already exist and are only referenced.
GENERATION_STATUS = postgresql.ENUM(
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
    name="generation_status",
    create_type=False,
)
GENERATION_PHASE = postgresql.ENUM(
    "document", "cross", name="generation_phase", create_type=False
)
GENERATED_KIND = postgresql.ENUM(
    "single", "multi", "cross", name="generated_kind", create_type=False
)
PROPOSAL_STATUS = postgresql.ENUM(
    "pending", "accepted", "rejected", name="proposal_status", create_type=False
)
EXECUTION_STATUS = postgresql.ENUM(name="execution_status", create_type=False)
RELEVANCE_GRADE = postgresql.ENUM(name="relevance_grade", create_type=False)
NEW_TYPES = (GENERATION_STATUS, GENERATION_PHASE, GENERATED_KIND, PROPOSAL_STATUS)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in NEW_TYPES:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "generation_jobs",
        sa.Column("qa_set_id", sa.UUID(), nullable=False),
        sa.Column("chunking_configuration_id", sa.UUID(), nullable=False),
        sa.Column("document_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column(
            "status", GENERATION_STATUS, server_default="pending", nullable=False
        ),
        sa.Column(
            "progress",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("workflow_id", sa.Text(), nullable=True),
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
            ["chunking_configuration_id"],
            ["chunking_configurations.id"],
            name=op.f(
                "fk_generation_jobs_chunking_configuration_id_chunking_configurations"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["qa_set_id"],
            ["qa_sets.id"],
            name=op.f("fk_generation_jobs_qa_set_id_qa_sets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generation_jobs")),
        sa.UniqueConstraint("workflow_id", name=op.f("uq_generation_jobs_workflow_id")),
    )
    op.create_index(
        op.f("ix_generation_jobs_chunking_configuration_id"),
        "generation_jobs",
        ["chunking_configuration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generation_jobs_qa_set_id"),
        "generation_jobs",
        ["qa_set_id"],
        unique=False,
    )
    op.create_table(
        "generation_units",
        sa.Column("generation_job_id", sa.UUID(), nullable=False),
        sa.Column("phase", GENERATION_PHASE, nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("target", sa.Integer(), nullable=False),
        sa.Column("produced", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", EXECUTION_STATUS, server_default="pending", nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "topics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "discards",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("end_reason", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("langfuse_trace_id", sa.Text(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_generation_units_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["generation_job_id"],
            ["generation_jobs.id"],
            name=op.f("fk_generation_units_generation_job_id_generation_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generation_units")),
    )
    op.create_index(
        "ix_generation_units_job_phase_status_position",
        "generation_units",
        ["generation_job_id", "phase", "status", "position"],
        unique=False,
    )
    op.create_table(
        "generated_questions",
        sa.Column("generation_job_id", sa.UUID(), nullable=False),
        sa.Column("unit_id", sa.UUID(), nullable=False),
        sa.Column("kind", GENERATED_KIND, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("status", PROPOSAL_STATUS, server_default="pending", nullable=False),
        sa.Column("accepted_question_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["accepted_question_id"],
            ["questions.id"],
            name=op.f("fk_generated_questions_accepted_question_id_questions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["generation_job_id"],
            ["generation_jobs.id"],
            name=op.f("fk_generated_questions_generation_job_id_generation_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"],
            ["generation_units.id"],
            name=op.f("fk_generated_questions_unit_id_generation_units"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generated_questions")),
    )
    op.create_index(
        op.f("ix_generated_questions_accepted_question_id"),
        "generated_questions",
        ["accepted_question_id"],
        unique=False,
    )
    op.create_index(
        "ix_generated_questions_job_status",
        "generated_questions",
        ["generation_job_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_questions_unit_id"),
        "generated_questions",
        ["unit_id"],
        unique=False,
    )
    op.create_table(
        "generated_question_chunks",
        sa.Column("generated_question_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("relevance", RELEVANCE_GRADE, nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.id"],
            name=op.f("fk_generated_question_chunks_chunk_id_chunks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_generated_question_chunks_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["generated_question_id"],
            ["generated_questions.id"],
            name=op.f(
                "fk_generated_question_chunks_generated_question_id_generated_questions"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "generated_question_id",
            "chunk_id",
            name=op.f("pk_generated_question_chunks"),
        ),
    )
    op.create_index(
        op.f("ix_generated_question_chunks_chunk_id"),
        "generated_question_chunks",
        ["chunk_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_question_chunks_document_id"),
        "generated_question_chunks",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_generated_question_chunks_document_id"),
        table_name="generated_question_chunks",
    )
    op.drop_index(
        op.f("ix_generated_question_chunks_chunk_id"),
        table_name="generated_question_chunks",
    )
    op.drop_table("generated_question_chunks")
    op.drop_index(
        op.f("ix_generated_questions_unit_id"), table_name="generated_questions"
    )
    op.drop_index("ix_generated_questions_job_status", table_name="generated_questions")
    op.drop_index(
        op.f("ix_generated_questions_accepted_question_id"),
        table_name="generated_questions",
    )
    op.drop_table("generated_questions")
    op.drop_index(
        "ix_generation_units_job_phase_status_position", table_name="generation_units"
    )
    op.drop_table("generation_units")
    op.drop_index(op.f("ix_generation_jobs_qa_set_id"), table_name="generation_jobs")
    op.drop_index(
        op.f("ix_generation_jobs_chunking_configuration_id"),
        table_name="generation_jobs",
    )
    op.drop_table("generation_jobs")

    bind = op.get_bind()
    for enum_type in reversed(NEW_TYPES):
        enum_type.drop(bind, checkfirst=True)
