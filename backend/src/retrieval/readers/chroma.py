from __future__ import annotations

import functools
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from src.components.builtin.contracts import VectorHit
from src.retrieval.distances import chroma_similarity

if TYPE_CHECKING:
    from chromadb.api import ClientAPI


class ChromaVectorStoreReader:
    """Read side of the Chroma collections written by index builds."""

    def __init__(self, client: ClientAPI) -> None:
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
        if document_ids is not None and not document_ids:
            return []
        target = self.client.get_collection(name=collection, embedding_function=None)
        space = _collection_space(target.configuration)
        where = (
            {"document_id": {"$in": list(document_ids)}}
            if document_ids is not None
            else None
        )
        result = target.query(
            query_embeddings=[list(vector)],
            n_results=top_k,
            where=where,
            include=["distances", "documents", "metadatas"],
        )
        ids = result["ids"][0]
        distances = (result["distances"] or [[]])[0]
        documents = (result["documents"] or [[None] * len(ids)])[0]
        metadatas = (result["metadatas"] or [[None] * len(ids)])[0]
        return [
            VectorHit(
                id=point_id,
                score=chroma_similarity(space, distance),
                document_id=(metadata or {}).get("document_id"),
                text=document,
            )
            for point_id, distance, document, metadata in zip(
                ids, distances, documents, metadatas, strict=True
            )
        ]


def _collection_space(configuration: dict[str, Any] | None) -> str:
    """The distance of a collection; Chroma's own default when none was configured."""
    hnsw = (configuration or {}).get("hnsw") or {}
    return hnsw.get("space") or "l2"


@functools.cache
def build_chroma_reader() -> ChromaVectorStoreReader:
    """Return a reader bound to the Chroma server configured in the settings.

    Cached for the life of the process: the HTTP client is reusable across requests, and
    building one per query would add a connection setup to every tool call.
    """
    import chromadb

    from src.settings import get_settings

    settings = get_settings()
    return ChromaVectorStoreReader(
        chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    )
