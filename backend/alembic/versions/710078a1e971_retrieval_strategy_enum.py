"""retrieval_profiles.strategy as an enum, without query_transforms

Revision ID: 710078a1e971
Revises: 004
Create Date: 2026-10-23 10:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from src.core.hashing import hash_json

# revision identifiers, used by Alembic.
revision = "710078a1e971"
down_revision = "004"
branch_labels = None
depends_on = None

RETRIEVAL_STRATEGY = postgresql.ENUM(
    "dense", "sparse", "hybrid", "multi_vector", name="retrieval_strategy"
)

# The columns the profile hash covers after this revision, and before it.
_HASHED_COLUMNS = ("top_k", "strategy", "score_threshold", "metadata_filters")
_PREVIOUS_HASHED_COLUMNS = (
    "top_k",
    "strategy",
    "pre_rerank_k",
    "fusion_weights",
    "mmr",
    "score_threshold",
    "metadata_filters",
    "query_transforms",
    "reranker_version_id",
    "context_policy",
)


def upgrade() -> None:
    RETRIEVAL_STRATEGY.create(op.get_bind(), checkfirst=True)
    op.alter_column(
        "retrieval_profiles",
        "strategy",
        type_=RETRIEVAL_STRATEGY,
        postgresql_using="strategy::retrieval_strategy",
    )
    # Rewriting the query belongs to the answer system, not to the vector store search.
    op.drop_column("retrieval_profiles", "query_transforms")
    _rehash(_HASHED_COLUMNS)


def downgrade() -> None:
    op.add_column(
        "retrieval_profiles",
        sa.Column(
            "query_transforms", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.alter_column(
        "retrieval_profiles",
        "strategy",
        type_=sa.Text(),
        postgresql_using="strategy::text",
    )
    RETRIEVAL_STRATEGY.drop(op.get_bind(), checkfirst=True)
    _rehash(_PREVIOUS_HASHED_COLUMNS)


def _rehash(hashed_columns: tuple[str, ...]) -> None:
    """Recompute every profile hash over the columns that exist after this step.

    Without this, an identical profile created after the migration would hash
    differently from the existing row and not be recognised as a duplicate.
    """
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f"SELECT id, {', '.join(hashed_columns)} FROM retrieval_profiles")
    ).mappings()
    for row in list(rows):
        values = {
            name: str(row[name])
            if name in ("strategy", "reranker_version_id") and row[name] is not None
            else row[name]
            for name in hashed_columns
        }
        bind.execute(
            sa.text("UPDATE retrieval_profiles SET config_hash = :hash WHERE id = :id"),
            {"hash": hash_json(values), "id": row["id"]},
        )
