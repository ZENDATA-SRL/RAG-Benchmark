from __future__ import annotations

import math
import uuid

import chromadb
import pytest
from chromadb.config import Settings
from qdrant_client import QdrantClient
from src.retrieval.distances import SPACES
from src.retrieval.readers.chroma import ChromaVectorStoreReader
from src.retrieval.readers.qdrant import QdrantVectorStoreReader

from temporal.components.vector_stores.chroma import ChromaVectorStore
from temporal.components.vector_stores.qdrant import QdrantVectorStore

# Three unit vectors and a unit query close to the first: the expected ranking is a, b, c on
# every distance, which is what makes one test valid for all three spaces.
_VECTORS = {
    "a": [1.0, 0.0, 0.0],
    "b": [0.6, 0.8, 0.0],
    "c": [0.0, 0.0, 1.0],
}
_QUERY = [0.96, 0.28, 0.0]


@pytest.fixture
def chroma_client():
    client = chromadb.EphemeralClient(settings=Settings(allow_reset=True))
    client.reset()
    return client


def _stores(chroma_client):
    """Writer and reader of each store, bound to the same in-process client."""
    qdrant_client = QdrantClient(":memory:")
    return {
        "chromadb": (
            ChromaVectorStore(chroma_client),
            ChromaVectorStoreReader(chroma_client),
        ),
        "qdrant": (
            QdrantVectorStore(qdrant_client),
            QdrantVectorStoreReader(qdrant_client),
        ),
    }


def _write(writer, name: str, index_params: dict) -> dict[str, str]:
    """Index the three vectors under chunk-like ids; return label -> id."""
    ids = {label: str(uuid.uuid4()) for label in _VECTORS}
    writer.ensure_collection(name, index_params)
    writer.upsert(
        name,
        ids=list(ids.values()),
        embeddings=list(_VECTORS.values()),
        documents=[f"text {label}" for label in _VECTORS],
        metadatas=[{"document_id": f"doc-{label}", "ordinal": 0} for label in _VECTORS],
        index_params=index_params,
    )
    return ids


def _expected(space: str, vector: list[float]) -> float:
    """The normalised score the readers promise: higher is better on every space."""
    if space == "l2":
        return 1.0 / (1.0 + math.dist(vector, _QUERY))
    return sum(x * y for x, y in zip(vector, _QUERY, strict=True))


@pytest.mark.parametrize("store", ["chromadb", "qdrant"])
@pytest.mark.parametrize("space", SPACES)
def test_reader_reads_back_what_the_writer_wrote(chroma_client, store, space) -> None:
    """Write and read share the distance mapping: ranking and scores must agree."""
    writer, reader = _stores(chroma_client)[store]
    name = f"idx_{uuid.uuid4().hex[:16]}"
    ids = _write(writer, name, {"space": space})

    hits = reader.query(name, _QUERY, top_k=3)

    assert [hit.id for hit in hits] == [ids["a"], ids["b"], ids["c"]]
    assert [hit.document_id for hit in hits] == ["doc-a", "doc-b", "doc-c"]
    assert hits[0].text == "text a"
    for hit, label in zip(hits, "abc", strict=True):
        assert hit.score == pytest.approx(_expected(space, _VECTORS[label]), abs=1e-4)


@pytest.mark.parametrize("store", ["chromadb", "qdrant"])
def test_a_profile_without_space_gets_the_same_distance_everywhere(
    chroma_client, store
) -> None:
    """Without the shared default Chroma would fall back to l2 and Qdrant to cosine."""
    writer, reader = _stores(chroma_client)[store]
    name = f"idx_{uuid.uuid4().hex[:16]}"
    _write(writer, name, {})

    hits = reader.query(name, _QUERY, top_k=1)

    assert hits[0].score == pytest.approx(_expected("cosine", _VECTORS["a"]), abs=1e-4)


@pytest.mark.parametrize("store", ["chromadb", "qdrant"])
def test_document_filter_restricts_the_search(chroma_client, store) -> None:
    writer, reader = _stores(chroma_client)[store]
    name = f"idx_{uuid.uuid4().hex[:16]}"
    ids = _write(writer, name, {"space": "cosine"})

    hits = reader.query(name, _QUERY, top_k=3, document_ids=["doc-b", "doc-c"])

    assert [hit.id for hit in hits] == [ids["b"], ids["c"]]


@pytest.mark.parametrize("store", ["chromadb", "qdrant"])
def test_an_empty_document_filter_matches_nothing(chroma_client, store) -> None:
    """An empty document restriction allows nothing: the answer is empty, not everything."""
    writer, reader = _stores(chroma_client)[store]
    name = f"idx_{uuid.uuid4().hex[:16]}"
    _write(writer, name, {"space": "cosine"})

    assert reader.query(name, _QUERY, top_k=3, document_ids=[]) == []
