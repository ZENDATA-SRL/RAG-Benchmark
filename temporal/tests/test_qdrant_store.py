from __future__ import annotations

import uuid

import pytest
from qdrant_client import QdrantClient

from temporal.components.vector_stores.qdrant import QdrantVectorStore


@pytest.fixture
def store() -> QdrantVectorStore:
    """In-process Qdrant: the real client code path, with no server to run."""
    return QdrantVectorStore(QdrantClient(":memory:"))


def _upsert(
    store: QdrantVectorStore,
    name: str,
    ids: list[str],
    text: str,
    index_params: dict | None = None,
) -> None:
    store.upsert(
        name,
        ids=ids,
        embeddings=[[1.0, 0.0, 0.0] for _ in ids],
        documents=[text for _ in ids],
        metadatas=[
            {"document_id": "d", "ordinal": index} for index, _ in enumerate(ids)
        ],
        index_params=index_params or {},
    )


def test_collection_takes_the_profile_configuration(store, monkeypatch) -> None:
    """The in-memory client ignores HNSW settings, so the arguments are checked instead."""
    name = f"idx_{uuid.uuid4().hex[:16]}"
    created: dict = {}
    create_collection = store.client.create_collection

    def record(**kwargs) -> None:
        created.update(kwargs)
        create_collection(**kwargs)

    monkeypatch.setattr(store.client, "create_collection", record)

    store.ensure_collection(name, {})
    _upsert(
        store,
        name,
        [str(uuid.uuid4())],
        "text",
        {"space": "ip", "max_neighbors": 8, "ef_construction": 64},
    )

    vectors = store.client.get_collection(name).config.params.vectors
    assert vectors.size == 3
    assert vectors.distance.value == "Dot"
    assert created["hnsw_config"].m == 8
    assert created["hnsw_config"].ef_construct == 64


def test_upsert_overwrites_by_id(store) -> None:
    """A retried batch must replace its own points, not duplicate them."""
    name = f"idx_{uuid.uuid4().hex[:16]}"
    ids = [str(uuid.uuid4()) for _ in range(3)]

    _upsert(store, name, ids, "first")
    _upsert(store, name, ids, "second")

    points, _ = store.client.scroll(name, limit=10)
    assert len(points) == 3
    assert {point.payload["document"] for point in points} == {"second"}


def test_empty_upsert_creates_nothing(store) -> None:
    name = f"idx_{uuid.uuid4().hex[:16]}"

    store.upsert(
        name, ids=[], embeddings=[], documents=[], metadatas=[], index_params={}
    )

    assert not store.client.collection_exists(name)
