from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from src.retrieval.distances import QDRANT_DISTANCES, profile_space

if TYPE_CHECKING:
    from qdrant_client import QdrantClient

KEY = "qdrant"


class QdrantVectorStore:
    """Write side of a Qdrant collection: one collection per index build."""

    def __init__(self, client: QdrantClient) -> None:
        self.client = client

    def ensure_collection(self, name: str, index_params: dict[str, Any]) -> None:
        """Do nothing: Qdrant needs the vector size, which is only known at the first upsert.

        The collection is created there with the profile's parameters.
        """

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

        The collection is created on the first batch, with the vector size taken from
        the embeddings and the profile's distance and HNSW configuration.
        """
        from qdrant_client import models

        if not ids:
            return
        if not self.client.collection_exists(name):
            distance = QDRANT_DISTANCES[profile_space(index_params)]
            hnsw = {
                argument: index_params[key]
                for key, argument in (
                    ("max_neighbors", "m"),
                    ("ef_construction", "ef_construct"),
                )
                if key in index_params
            }
            self.client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=len(embeddings[0]), distance=models.Distance(distance)
                ),
                hnsw_config=models.HnswConfigDiff(**hnsw) if hnsw else None,
            )
        self.client.upsert(
            collection_name=name,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=list(vector),
                    payload={**metadata, "document": document},
                )
                for point_id, vector, document, metadata in zip(
                    ids, embeddings, documents, metadatas, strict=True
                )
            ],
        )


def build_qdrant_store() -> QdrantVectorStore:
    """Return a store bound to the Qdrant server configured in the settings."""
    from qdrant_client import QdrantClient
    from src.settings import get_settings

    settings = get_settings()
    return QdrantVectorStore(
        QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    )
