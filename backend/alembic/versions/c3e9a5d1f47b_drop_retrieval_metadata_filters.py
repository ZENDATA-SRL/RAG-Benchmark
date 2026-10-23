"""drop retrieval_profiles.metadata_filters

Revision ID: c3e9a5d1f47b
Revises: 710078a1e971
Create Date: 2026-10-23 12:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from src.core.hashing import hash_json

# revision identifiers, used by Alembic.
revision = "c3e9a5d1f47b"
down_revision = "710078a1e971"
branch_labels = None
depends_on = None

# The columns the profile hash covers after this revision, and before it.
_HASHED_COLUMNS = ("top_k", "strategy", "score_threshold")
_PREVIOUS_HASHED_COLUMNS = ("top_k", "strategy", "score_threshold", "metadata_filters")


def upgrade() -> None:
    # A filter on document metadata restricts the search space, which the corpus snapshot
    # already fixes for every variant of an experiment: in the profile it would let two
    # variants search different documents. Restricting the documents is a snapshot's job.
    op.drop_column("retrieval_profiles", "metadata_filters")
    _rehash(_HASHED_COLUMNS)


def downgrade() -> None:
    op.add_column(
        "retrieval_profiles",
        sa.Column(
            "metadata_filters", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    _rehash(_PREVIOUS_HASHED_COLUMNS)


def _rehash(hashed_columns: tuple[str, ...]) -> None:
    """Recompute every profile hash over the columns that exist after this step.

    Without this, an identical profile created after the migration would hash
    differently from the existing row and not be recognised as a duplicate. Profiles
    that differed only by the dropped column now share a hash: the oldest is kept and
    the others are deleted, which is safe because nothing references a retrieval
    profile yet.
    """
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            f"SELECT id, {', '.join(hashed_columns)} FROM retrieval_profiles "
            "ORDER BY created_at, id"
        )
    ).mappings()
    seen: set[str] = set()
    for row in list(rows):
        values = {
            name: str(row[name])
            if name == "strategy" and row[name] is not None
            else row[name]
            for name in hashed_columns
        }
        digest = hash_json(values)
        if digest in seen:
            bind.execute(
                sa.text("DELETE FROM retrieval_profiles WHERE id = :id"),
                {"id": row["id"]},
            )
            continue
        seen.add(digest)
        bind.execute(
            sa.text("UPDATE retrieval_profiles SET config_hash = :hash WHERE id = :id"),
            {"hash": digest, "id": row["id"]},
        )
