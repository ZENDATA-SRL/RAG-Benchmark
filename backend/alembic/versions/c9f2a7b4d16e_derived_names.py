"""derived names

Revision ID: c9f2a7b4d16e
Revises: b8e1f6a3c959
Create Date: 2026-10-28 12:10:00.000000

"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from src.pipelines import naming

# revision identifiers, used by Alembic.
revision = "c9f2a7b4d16e"
down_revision = "b8e1f6a3c959"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename profiles, configurations, index builds and variants after what they are.

    Rows are renamed oldest first, so when two would read the same the older keeps the
    plain name and the newer one gains the hash suffix, as on creation. Each level is
    renamed before the levels whose names are composed from it.
    """
    bind = op.get_bind()
    components = {
        row["id"]: (naming.component_label(row["key"], row["version"]), row["schema"])
        for row in bind.execute(
            sa.text(
                "SELECT v.id, c.key, v.version, v.params_schema AS schema "
                "FROM component_versions v JOIN components c ON c.id = v.component_id"
            )
        ).mappings()
    }

    def component(row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        label, schema = components[row["component_version_id"]]
        return label, schema or {}

    def parsing(row: dict[str, Any]) -> str:
        return naming.parsing_profile_name(component(row)[0])

    def chunking(row: dict[str, Any]) -> str:
        label, schema = component(row)
        params = dict(row["params"] or {})
        for key in ("chunk_size", "overlap"):
            if row[key] is not None:
                params.setdefault(key, row[key])
        return naming.chunking_profile_name(
            label,
            chunk_size=naming.schema_value(params, schema, "chunk_size"),
            overlap=naming.schema_value(params, schema, "overlap"),
        )

    def embedding(row: dict[str, Any]) -> str:
        label, schema = component(row)
        return naming.embedding_profile_name(
            label,
            model=naming.schema_value(row["params"] or {}, schema, "model_name"),
            dimensions=row["dimensions"],
        )

    def vector_store(row: dict[str, Any]) -> str:
        label, schema = component(row)
        return naming.vector_store_profile_name(
            label, space=naming.schema_value(row["index_params"] or {}, schema, "space")
        )

    def retrieval(row: dict[str, Any]) -> str:
        return naming.retrieval_profile_name(
            row["strategy"], top_k=row["top_k"], score_threshold=row["score_threshold"]
        )

    profiles = {
        "parsing_profiles": _rename(
            bind, "parsing_profiles", "*", "config_hash", parsing
        ),
        "chunking_profiles": _rename(
            bind, "chunking_profiles", "*", "config_hash", chunking
        ),
        "embedding_profiles": _rename(
            bind, "embedding_profiles", "*", "config_hash", embedding
        ),
        "vector_store_profiles": _rename(
            bind, "vector_store_profiles", "*", "config_hash", vector_store
        ),
        "retrieval_profiles": _rename(
            bind,
            "retrieval_profiles",
            "id, created_at, config_hash, strategy::text AS strategy, top_k, "
            "score_threshold",
            "config_hash",
            retrieval,
        ),
    }
    configurations = _rename(
        bind,
        "chunking_configurations",
        "*",
        "config_hash",
        lambda row: naming.chunking_configuration_name(
            profiles["parsing_profiles"][row["parsing_profile_id"]],
            profiles["chunking_profiles"][row["chunking_profile_id"]],
        ),
    )
    _rename(
        bind,
        "index_builds b JOIN corpus_snapshots s ON s.id = b.corpus_snapshot_id "
        "JOIN corpora c ON c.id = s.corpus_id",
        "b.id, b.created_at, b.chain_fingerprint, b.chunking_configuration_id, "
        "b.embedding_profile_id, b.vector_store_profile_id, s.label, c.name AS corpus",
        "chain_fingerprint",
        lambda row: naming.index_build_name(
            row["corpus"],
            row["label"],
            configurations[row["chunking_configuration_id"]],
            profiles["embedding_profiles"][row["embedding_profile_id"]],
            profiles["vector_store_profiles"][row["vector_store_profile_id"]],
        ),
        table="index_builds",
        order="b.created_at, b.id",
    )
    variants = bind.execute(
        sa.text(
            "SELECT v.id, v.retrieval_profile_id, b.chunking_configuration_id, "
            "b.embedding_profile_id, b.vector_store_profile_id "
            "FROM variants v JOIN index_builds b ON b.id = v.index_build_id"
        )
    ).mappings()
    for row in list(variants):
        bind.execute(
            sa.text("UPDATE variants SET name = :name WHERE id = :id"),
            {
                "id": row["id"],
                "name": naming.variant_name(
                    configurations[row["chunking_configuration_id"]],
                    profiles["embedding_profiles"][row["embedding_profile_id"]],
                    profiles["vector_store_profiles"][row["vector_store_profile_id"]],
                    profiles["retrieval_profiles"][row["retrieval_profile_id"]],
                ),
            },
        )


def downgrade() -> None:
    """Nothing to undo: the names typed before are not kept, and the derived ones work."""


def _rename(
    bind: sa.Connection,
    source: str,
    columns: str,
    digest_column: str,
    derive: Any,
    *,
    table: str | None = None,
    order: str = "created_at, id",
) -> dict[Any, str]:
    """Rename every row of a table with `derive`, oldest first; returns the new names."""
    names: dict[Any, str] = {}
    taken: set[str] = set()
    rows = bind.execute(sa.text(f"SELECT {columns} FROM {source} ORDER BY {order}"))
    for row in list(rows.mappings()):
        base = derive(dict(row))
        name = naming.disambiguated(base, row[digest_column], taken=base in taken)
        taken.add(base)
        names[row["id"]] = name
        bind.execute(
            sa.text(f"UPDATE {table or source} SET name = :name WHERE id = :id"),
            {"name": name, "id": row["id"]},
        )
    return names
