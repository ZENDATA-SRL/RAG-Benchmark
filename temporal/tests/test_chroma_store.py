from __future__ import annotations

import uuid

import chromadb
import pytest
from chromadb.config import Settings

from temporal.components.vector_stores.chroma import ChromaVectorStore


@pytest.fixture
def store() -> ChromaVectorStore:
    """In-process Chroma: the real client code path, with no server to run."""
    client = chromadb.EphemeralClient(settings=Settings(allow_reset=True))
    client.reset()
    return ChromaVectorStore(client)


def _upsert(store: ChromaVectorStore, name: str, ids: list[str], text: str) -> None:
    store.upsert(
        name,
        ids=ids,
        embeddings=[[1.0, 0.0, 0.0] for _ in ids],
        documents=[text for _ in ids],
        metadatas=[
            {"document_id": "d", "ordinal": index} for index, _ in enumerate(ids)
        ],
    )


def test_collection_takes_the_profile_hnsw_configuration(store) -> None:
    name = f"idx_{uuid.uuid4().hex[:16]}"

    store.ensure_collection(
        name, {"space": "ip", "max_neighbors": 8, "unrelated_option": True}
    )

    configuration = store.client.get_collection(name).configuration
    assert configuration["hnsw"]["space"] == "ip"
    assert configuration["hnsw"]["max_neighbors"] == 8


def test_ensure_collection_is_idempotent(store) -> None:
    name = f"idx_{uuid.uuid4().hex[:16]}"

    store.ensure_collection(name, {"space": "cosine"})
    store.ensure_collection(name, {"space": "cosine"})

    assert [collection.name for collection in store.client.list_collections()] == [name]


def test_a_retried_batch_overwrites_itself(store) -> None:
    """Upsert keyed by chunk id: re-running a batch never duplicates vectors."""
    name = f"idx_{uuid.uuid4().hex[:16]}"
    store.ensure_collection(name, {})
    ids = [str(uuid.uuid4()) for _ in range(3)]

    _upsert(store, name, ids, "first")
    _upsert(store, name, ids, "second")

    collection = store.client.get_collection(name)
    stored = collection.get(ids=ids, include=["documents", "metadatas"])
    assert collection.count() == 3
    assert set(stored["documents"]) == {"second"}
    assert {metadata["document_id"] for metadata in stored["metadatas"]} == {"d"}


def test_empty_batch_is_a_no_op(store) -> None:
    name = f"idx_{uuid.uuid4().hex[:16]}"
    store.ensure_collection(name, {})

    store.upsert(name, ids=[], embeddings=[], documents=[], metadatas=[])

    assert store.client.get_collection(name).count() == 0
