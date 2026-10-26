"""qa sets and experiments

Revision ID: d4a7b2c9e515
Revises: c3e9a5d1f47b
Create Date: 2026-10-23 18:38:10.355765

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "d4a7b2c9e515"
down_revision = "c3e9a5d1f47b"
branch_labels = None
depends_on = None

# Each type is shared by several columns (`execution_status` by runs and executions), so
# they are created and dropped explicitly and referenced with `create_type=False`.
METRIC_FAMILY = postgresql.ENUM(
    "retrieval",
    "answer",
    "efficiency",
    "robustness",
    name="metric_family",
    create_type=False,
)
METRIC_LEVEL = postgresql.ENUM(
    "document",
    "chunk",
    name="metric_level",
    create_type=False,
)
EVALUATOR_KIND = postgresql.ENUM(
    "deterministic",
    "llm_judge",
    "human",
    name="evaluator_kind",
    create_type=False,
)
EXPERIMENT_TYPE = postgresql.ENUM(
    "retrieval",
    "qa",
    name="experiment_type",
    create_type=False,
)
RETRIEVAL_SCOPE = postgresql.ENUM(
    "retrieved",
    "in_context",
    "cited",
    name="retrieval_scope",
    create_type=False,
)
EXECUTION_STATUS = postgresql.ENUM(
    "pending",
    "running",
    "succeeded",
    "failed",
    "skipped",
    name="execution_status",
    create_type=False,
)
RETRIEVAL_STAGE = postgresql.ENUM(
    "dense",
    "sparse",
    "fused",
    "reranked",
    "final",
    name="retrieval_stage",
    create_type=False,
)

ENUM_TYPES = (
    METRIC_FAMILY,
    METRIC_LEVEL,
    EVALUATOR_KIND,
    EXPERIMENT_TYPE,
    RETRIEVAL_SCOPE,
    EXECUTION_STATUS,
    RETRIEVAL_STAGE,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in ENUM_TYPES:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "metric_definitions",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("family", METRIC_FAMILY, nullable=False),
        sa.Column("level", METRIC_LEVEL, nullable=True),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("aggregation", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metric_definitions")),
        sa.UniqueConstraint("key", name=op.f("uq_metric_definitions_key")),
    )
    op.create_table(
        "qa_sets",
        sa.Column("origin_corpus_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["origin_corpus_id"],
            ["corpora.id"],
            name=op.f("fk_qa_sets_origin_corpus_id_corpora"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qa_sets")),
    )
    op.create_index(
        op.f("ix_qa_sets_origin_corpus_id"),
        "qa_sets",
        ["origin_corpus_id"],
        unique=False,
    )
    op.create_table(
        "evaluators",
        sa.Column("kind", EVALUATOR_KIND, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("component_version_id", sa.UUID(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("rubric", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("version", sa.Text(), nullable=False),
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
            name=op.f("fk_evaluators_component_version_id_component_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluators")),
    )
    op.create_index(
        op.f("ix_evaluators_component_version_id"),
        "evaluators",
        ["component_version_id"],
        unique=False,
    )
    op.create_table(
        "qa_set_snapshots",
        sa.Column("qa_set_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("composition_hash", sa.Text(), nullable=False),
        sa.Column("langfuse_dataset_id", sa.Text(), nullable=True),
        sa.Column(
            "frozen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["qa_set_id"],
            ["qa_sets.id"],
            name=op.f("fk_qa_set_snapshots_qa_set_id_qa_sets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qa_set_snapshots")),
        sa.UniqueConstraint(
            "qa_set_id",
            "composition_hash",
            name=op.f("uq_qa_set_snapshots_qa_set_id_composition_hash"),
        ),
    )
    op.create_index(
        op.f("ix_qa_set_snapshots_composition_hash"),
        "qa_set_snapshots",
        ["composition_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_qa_set_snapshots_qa_set_id"),
        "qa_set_snapshots",
        ["qa_set_id"],
        unique=False,
    )
    op.create_table(
        "questions",
        sa.Column("qa_set_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "attachments",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "answerable", sa.Boolean(), server_default=sa.text("true"), nullable=False
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
            ["qa_set_id"],
            ["qa_sets.id"],
            name=op.f("fk_questions_qa_set_id_qa_sets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questions")),
    )
    op.create_index(
        op.f("ix_questions_qa_set_id"), "questions", ["qa_set_id"], unique=False
    )
    op.create_index(
        "ix_questions_tags", "questions", ["tags"], unique=False, postgresql_using="gin"
    )
    op.create_table(
        "experiments",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", EXPERIMENT_TYPE, nullable=False),
        sa.Column("corpus_snapshot_id", sa.UUID(), nullable=False),
        sa.Column("qa_set_snapshot_id", sa.UUID(), nullable=False),
        sa.Column("repetitions", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "retrieval_scope",
            RETRIEVAL_SCOPE,
            server_default="retrieved",
            nullable=False,
        ),
        sa.Column("uncovered_policy", sa.Text(), nullable=True),
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
            ["corpus_snapshot_id"],
            ["corpus_snapshots.id"],
            name=op.f("fk_experiments_corpus_snapshot_id_corpus_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["qa_set_snapshot_id"],
            ["qa_set_snapshots.id"],
            name=op.f("fk_experiments_qa_set_snapshot_id_qa_set_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiments")),
    )
    op.create_index(
        op.f("ix_experiments_corpus_snapshot_id"),
        "experiments",
        ["corpus_snapshot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_experiments_qa_set_snapshot_id"),
        "experiments",
        ["qa_set_snapshot_id"],
        unique=False,
    )
    op.create_table(
        "gold_documents",
        sa.Column("question_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
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
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_gold_documents_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_gold_documents_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gold_documents")),
        sa.UniqueConstraint(
            "question_id",
            "document_id",
            name=op.f("uq_gold_documents_question_id_document_id"),
        ),
    )
    op.create_index(
        op.f("ix_gold_documents_document_id"),
        "gold_documents",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_gold_documents_question_id"),
        "gold_documents",
        ["question_id"],
        unique=False,
    )
    op.create_table(
        "qa_snapshot_questions",
        sa.Column("snapshot_id", sa.UUID(), nullable=False),
        sa.Column("question_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_qa_snapshot_questions_question_id_questions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["qa_set_snapshots.id"],
            name=op.f("fk_qa_snapshot_questions_snapshot_id_qa_set_snapshots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "snapshot_id", "question_id", name=op.f("pk_qa_snapshot_questions")
        ),
    )
    op.create_table(
        "runs",
        sa.Column("experiment_id", sa.UUID(), nullable=False),
        sa.Column("workflow_id", sa.Text(), nullable=True),
        sa.Column("status", EXECUTION_STATUS, server_default="pending", nullable=False),
        sa.Column(
            "config_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "progress",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("langfuse_run_name", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
            ["experiment_id"],
            ["experiments.id"],
            name=op.f("fk_runs_experiment_id_experiments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runs")),
        sa.UniqueConstraint("workflow_id", name=op.f("uq_runs_workflow_id")),
    )
    op.create_index(
        op.f("ix_runs_experiment_id"), "runs", ["experiment_id"], unique=False
    )
    op.create_table(
        "variants",
        sa.Column("experiment_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("index_build_id", sa.UUID(), nullable=False),
        sa.Column("retrieval_profile_id", sa.UUID(), nullable=False),
        sa.Column("answer_profile_id", sa.UUID(), nullable=True),
        sa.Column(
            "is_baseline", sa.Boolean(), server_default=sa.text("false"), nullable=False
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
            ["experiment_id"],
            ["experiments.id"],
            name=op.f("fk_variants_experiment_id_experiments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["index_build_id"],
            ["index_builds.id"],
            name=op.f("fk_variants_index_build_id_index_builds"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_profile_id"],
            ["retrieval_profiles.id"],
            name=op.f("fk_variants_retrieval_profile_id_retrieval_profiles"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_variants")),
    )
    op.create_index(
        op.f("ix_variants_experiment_id"), "variants", ["experiment_id"], unique=False
    )
    op.create_index(
        op.f("ix_variants_index_build_id"), "variants", ["index_build_id"], unique=False
    )
    op.create_index(
        op.f("ix_variants_retrieval_profile_id"),
        "variants",
        ["retrieval_profile_id"],
        unique=False,
    )
    op.create_table(
        "executions",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("variant_id", sa.UUID(), nullable=False),
        sa.Column("question_id", sa.UUID(), nullable=False),
        sa.Column("repetition", sa.Integer(), nullable=False),
        sa.Column("status", EXECUTION_STATUS, server_default="pending", nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("refused", sa.Boolean(), nullable=True),
        sa.Column("answer_payload_uri", sa.Text(), nullable=True),
        sa.Column("usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("timings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("langfuse_trace_id", sa.Text(), nullable=True),
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
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_executions_question_id_questions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            name=op.f("fk_executions_run_id_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["variants.id"],
            name=op.f("fk_executions_variant_id_variants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_executions")),
        sa.UniqueConstraint(
            "run_id",
            "variant_id",
            "question_id",
            "repetition",
            name=op.f("uq_executions_run_id_variant_id_question_id_repetition"),
        ),
    )
    op.create_index(
        "ix_executions_run_id_variant_id",
        "executions",
        ["run_id", "variant_id"],
        unique=False,
    )
    op.create_table(
        "metric_aggregates",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("variant_id", sa.UUID(), nullable=False),
        sa.Column("metric_definition_id", sa.UUID(), nullable=False),
        sa.Column("slice_key", sa.Text(), server_default="all", nullable=False),
        sa.Column("slice_value", sa.Text(), server_default="all", nullable=False),
        sa.Column("mean", sa.Double(), nullable=True),
        sa.Column("stddev", sa.Double(), nullable=True),
        sa.Column("median", sa.Double(), nullable=True),
        sa.Column("p95", sa.Double(), nullable=True),
        sa.Column("ci_low", sa.Double(), nullable=True),
        sa.Column("ci_high", sa.Double(), nullable=True),
        sa.Column("n_effective", sa.Integer(), nullable=False),
        sa.Column("n_excluded", sa.Integer(), server_default="0", nullable=False),
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
            ["metric_definition_id"],
            ["metric_definitions.id"],
            name=op.f("fk_metric_aggregates_metric_definition_id_metric_definitions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            name=op.f("fk_metric_aggregates_run_id_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["variants.id"],
            name=op.f("fk_metric_aggregates_variant_id_variants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metric_aggregates")),
        sa.UniqueConstraint(
            "run_id",
            "variant_id",
            "metric_definition_id",
            "slice_key",
            "slice_value",
            name=op.f(
                "uq_metric_aggregates_run_id_variant_id_metric_definition_id_slice_key_slice_value"
            ),
        ),
    )
    op.create_table(
        "evaluations",
        sa.Column("execution_id", sa.UUID(), nullable=False),
        sa.Column("metric_definition_id", sa.UUID(), nullable=False),
        sa.Column("evaluator_id", sa.UUID(), nullable=False),
        sa.Column("score", sa.Double(), nullable=True),
        sa.Column(
            "excluded", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("exclusion_reason", sa.Text(), nullable=True),
        sa.Column("langfuse_score_id", sa.Text(), nullable=True),
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
            ["evaluator_id"],
            ["evaluators.id"],
            name=op.f("fk_evaluations_evaluator_id_evaluators"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["executions.id"],
            name=op.f("fk_evaluations_execution_id_executions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["metric_definition_id"],
            ["metric_definitions.id"],
            name=op.f("fk_evaluations_metric_definition_id_metric_definitions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluations")),
        sa.UniqueConstraint(
            "execution_id",
            "metric_definition_id",
            "evaluator_id",
            name=op.f("uq_evaluations_execution_id_metric_definition_id_evaluator_id"),
        ),
    )
    op.create_table(
        "retrieval_calls",
        sa.Column("execution_id", sa.UUID(), nullable=False),
        sa.Column("call_index", sa.Integer(), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
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
            ["execution_id"],
            ["executions.id"],
            name=op.f("fk_retrieval_calls_execution_id_executions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retrieval_calls")),
        sa.UniqueConstraint(
            "execution_id",
            "call_index",
            name=op.f("uq_retrieval_calls_execution_id_call_index"),
        ),
    )
    op.create_table(
        "retrieval_hits",
        sa.Column("retrieval_call_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Double(), nullable=True),
        sa.Column("stage", RETRIEVAL_STAGE, nullable=False),
        sa.Column(
            "in_context", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "cited", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("relevant_document", sa.Boolean(), nullable=True),
        sa.Column("relevant_chunk", sa.Boolean(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.id"],
            name=op.f("fk_retrieval_hits_chunk_id_chunks"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_call_id"],
            ["retrieval_calls.id"],
            name=op.f("fk_retrieval_hits_retrieval_call_id_retrieval_calls"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retrieval_hits")),
    )
    op.create_index(
        "ix_retrieval_hits_retrieval_call_id_stage_rank",
        "retrieval_hits",
        ["retrieval_call_id", "stage", "rank"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_retrieval_hits_retrieval_call_id_stage_rank", table_name="retrieval_hits"
    )
    op.drop_table("retrieval_hits")
    op.drop_table("retrieval_calls")
    op.drop_table("evaluations")
    op.drop_table("metric_aggregates")
    op.drop_index("ix_executions_run_id_variant_id", table_name="executions")
    op.drop_table("executions")
    op.drop_index(op.f("ix_variants_retrieval_profile_id"), table_name="variants")
    op.drop_index(op.f("ix_variants_index_build_id"), table_name="variants")
    op.drop_index(op.f("ix_variants_experiment_id"), table_name="variants")
    op.drop_table("variants")
    op.drop_index(op.f("ix_runs_experiment_id"), table_name="runs")
    op.drop_table("runs")
    op.drop_table("qa_snapshot_questions")
    op.drop_index(op.f("ix_gold_documents_question_id"), table_name="gold_documents")
    op.drop_index(op.f("ix_gold_documents_document_id"), table_name="gold_documents")
    op.drop_table("gold_documents")
    op.drop_index(op.f("ix_experiments_qa_set_snapshot_id"), table_name="experiments")
    op.drop_index(op.f("ix_experiments_corpus_snapshot_id"), table_name="experiments")
    op.drop_table("experiments")
    op.drop_index("ix_questions_tags", table_name="questions", postgresql_using="gin")
    op.drop_index(op.f("ix_questions_qa_set_id"), table_name="questions")
    op.drop_table("questions")
    op.drop_index(op.f("ix_qa_set_snapshots_qa_set_id"), table_name="qa_set_snapshots")
    op.drop_index(
        op.f("ix_qa_set_snapshots_composition_hash"), table_name="qa_set_snapshots"
    )
    op.drop_table("qa_set_snapshots")
    op.drop_index(op.f("ix_evaluators_component_version_id"), table_name="evaluators")
    op.drop_table("evaluators")
    op.drop_index(op.f("ix_qa_sets_origin_corpus_id"), table_name="qa_sets")
    op.drop_table("qa_sets")
    op.drop_table("metric_definitions")
    for enum_type in reversed(ENUM_TYPES):
        enum_type.drop(op.get_bind(), checkfirst=True)
