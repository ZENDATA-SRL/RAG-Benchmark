from __future__ import annotations

import functools
from collections.abc import Sequence
from typing import TYPE_CHECKING

from src.components.builtin.contracts import VectorHit
from src.retrieval.distances import SPACES_BY_QDRANT_DISTANCE, qdrant_similarity

if TYPE_CHECKING:
    from qdrant_client import QdrantClient


class QdrantVectorStoreReader:
    """Read side of the Qdrant collections written by index builds."""

    def __init__(self, client: QdrantClient) -> None:
        self.client = client

    def query(
        self,
        collection: str,
        vector: Sequence[float],
        *,
        top_k: int,
        document_ids: Sequence[str] | None = None,
    ) -> list[VectorHit]:
        """Return the `top_k` nearest chunks, best first, with normalised scores.

        The distance is read from the collection rather than from the profile: the
        collection is what the vectors were actually indexed with.
        """
        from qdrant_client import models

        if document_ids is not None and not document_ids:
            return []
        distance = self.client.get_collection(collection).config.params.vectors.distance
        space = SPACES_BY_QDRANT_DISTANCE[distance.value]
        query_filter = (
            models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchAny(any=list(document_ids)),
                    )
                ]
            )
            if document_ids is not None
            else None
        )
        response = self.client.query_points(
            collection_name=collection,
            query=list(vector),
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        return [
            VectorHit(
                id=str(point.id),
                score=qdrant_similarity(space, point.score),
                document_id=(point.payload or {}).get("document_id"),
                text=(point.payload or {}).get("document"),
            )
            for point in response.points
        ]


@functools.cache
def build_qdrant_reader() -> QdrantVectorStoreReader:
    """Return a reader bound to the Qdrant server configured in the settings.

    Cached for the life of the process: the client keeps its connection pool across
    requests.
    """
    from qdrant_client import QdrantClient

    from src.settings import get_settings

    settings = get_settings()
    return QdrantVectorStoreReader(
        QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    )
