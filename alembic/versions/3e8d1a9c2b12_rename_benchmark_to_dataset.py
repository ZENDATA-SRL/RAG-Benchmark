"""rename benchmark to dataset

Revision ID: 3e8d1a9c2b12
Revises: faf7fed1c54f
Create Date: 2026-04-08

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3e8d1a9c2b12"
down_revision = "faf7fed1c54f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("benchmarks", "datasets")

    op.alter_column(
        "documents",
        "benchmark_id",
        new_column_name="dataset_id",
        existing_type=sa.UUID(),
        existing_nullable=False,
    )
    op.alter_column(
        "questions",
        "benchmark_id",
        new_column_name="dataset_id",
        existing_type=sa.UUID(),
        existing_nullable=False,
    )

    # FKs created in the initial migration are unnamed in code but will get
    # deterministic names from PostgreSQL. We drop by convention name and
    # recreate with explicit names to avoid ambiguity going forward.
    op.drop_constraint("documents_benchmark_id_fkey", "documents", type_="foreignkey")
    op.drop_constraint("questions_benchmark_id_fkey", "questions", type_="foreignkey")

    op.create_foreign_key(
        "documents_dataset_id_fkey",
        "documents",
        "datasets",
        ["dataset_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "questions_dataset_id_fkey",
        "questions",
        "datasets",
        ["dataset_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("questions_dataset_id_fkey", "questions", type_="foreignkey")
    op.drop_constraint("documents_dataset_id_fkey", "documents", type_="foreignkey")

    op.create_foreign_key(
        "questions_benchmark_id_fkey",
        "questions",
        "benchmarks",
        ["benchmark_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "documents_benchmark_id_fkey",
        "documents",
        "benchmarks",
        ["benchmark_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.alter_column(
        "questions",
        "dataset_id",
        new_column_name="benchmark_id",
        existing_type=sa.UUID(),
        existing_nullable=False,
    )
    op.alter_column(
        "documents",
        "dataset_id",
        new_column_name="benchmark_id",
        existing_type=sa.UUID(),
        existing_nullable=False,
    )

    op.rename_table("datasets", "benchmarks")

