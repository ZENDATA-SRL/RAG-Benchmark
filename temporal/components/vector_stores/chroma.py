from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from src.retrieval.distances import profile_space

if TYPE_CHECKING:
    from chromadb.api import ClientAPI

KEY = "chromadb"

# The profile schema allows extra properties, but only these reach Chroma: anything else
# would be rejected by the collection configuration.
_HNSW_KEYS = (
    "space",
    "ef_construction",
    "ef_search",
    "max_neighbors",
    "num_threads",
    "batch_size",
    "sync_threshold",
    "resize_factor",
)


class ChromaVectorStore:
    """Write side of a Chroma collection: one collection per index build."""

    def __init__(self, client: ClientAPI) -> None:
        self.client = client

    def ensure_collection(self, name: str, index_params: dict[str, Any]) -> None:
        """Create the collection with the profile's HNSW configuration, or reuse it.

        The configuration is only applied at creation: re-running a build reuses the
        collection as it is, which is safe because the upsert is keyed by chunk id. The
        space is always set, so a profile without one gets the shared default and not
        Chroma's own.
        """
        hnsw = {key: index_params[key] for key in _HNSW_KEYS if key in index_params}
        hnsw["space"] = profile_space(index_params)
        self.client.get_or_create_collection(
            name=name,
            configuration={"hnsw": hnsw},
            # Vectors are computed by the embedding profile, never by Chroma.
            embedding_function=None,
        )

    def upsert(
        self,
        name: str,
        *,
        ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        documents: Sequence[str],
        metadatas: Sequence[dict[str, Any]],
        index_params: dict[str, Any],
    ) -> None:
        """Insert or replace vectors by id, so a retried batch overwrites itself.

        `index_params` is unused: Chroma applies it when the collection is created.
        """
        if not ids:
            return
        collection = self.client.get_collection(name=name, embedding_function=None)
        collection.upsert(
            ids=list(ids),
            embeddings=[list(vector) for vector in embeddings],
            documents=list(documents),
            metadatas=[dict(metadata) for metadata in metadatas],
        )


def build_chroma_store() -> ChromaVectorStore:
    """Return a store bound to the Chroma server configured in the settings."""
    import chromadb
    from src.settings import get_settings

    settings = get_settings()
    return ChromaVectorStore(
        chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    )
