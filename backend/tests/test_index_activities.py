from __future__ import annotations

import contextlib
import uuid

import chromadb
import pytest
from chromadb.config import Settings as ChromaSettings
from langchain_core.embeddings import DeterministicFakeEmbedding
from src.components.builtin.embedder import openai_embedder
from src.components.builtin.vector_stores import chroma
from src.components.repository import ComponentRepository, ComponentVersionRepository
from src.corpora.service import CorpusSnapshotService
from src.indexes.service import IndexBuildService
from src.infrastructure.database.enums import ComponentType
from src.pipelines.service import ProfileService
from temporalio.exceptions import ApplicationError
from tests.pipeline_factory import Scenario, build_scenario

from temporal.activities import embed, vector_store
from temporal.components import BUILTIN_VECTOR_STORES
from temporal.components.embedders.shared import BUILTIN_EMBEDDERS
from temporal.components.vector_stores.chroma import ChromaVectorStore

pytestmark = pytest.mark.integration

_DIMENSIONS = 4


@pytest.fixture
def chroma_client():
    client = chromadb.EphemeralClient(settings=ChromaSettings(allow_reset=True))
    client.reset()
    return client


@pytest.fixture
def worker(monkeypatch, session, fake_storage, chroma_client):
    """Run the real activities on the test transaction, storage and an in-process Chroma.

    Only the embedder is fake: everything the feature owns (queries, storage keys, record
    layout, upsert) runs for real.
    """

    @contextlib.asynccontextmanager
    async def test_session():
        yield session
        await session.flush()

    for module in (embed, vector_store):
        monkeypatch.setattr(module, "activity_session", test_session)
    monkeypatch.setattr(embed, "_storage", lambda: fake_storage)
    monkeypatch.setattr(vector_store, "get_object_storage", lambda _: fake_storage)
    monkeypatch.setitem(
        BUILTIN_EMBEDDERS,
        openai_embedder.KEY,
        lambda params: DeterministicFakeEmbedding(size=_DIMENSIONS),
    )
    monkeypatch.setitem(
        BUILTIN_VECTOR_STORES, chroma.KEY, lambda: ChromaVectorStore(chroma_client)
    )


async def _version_id(session, component_type: ComponentType, key: str) -> uuid.UUID:
    component = await ComponentRepository(session).get_by_type_and_key(
        component_type, key
    )
    assert component is not None
    return (await ComponentVersionRepository(session).list_versions(component.id))[0].id


async def _build(session, scenario: Scenario, *, dimensions: int) -> tuple[str, str]:
    """An index build over every ready document; returns its id and embedding profile id."""
    profiles = ProfileService(session)
    embedding, _ = await profiles.get_or_create_embedding_profile(
        name="fake",
        component_version_id=await _version_id(
            session, ComponentType.EMBEDDER, openai_embedder.KEY
        ),
        dimensions=dimensions,
    )
    vector_store_profile, _ = await profiles.get_or_create_vector_store_profile(
        name="chroma",
        component_version_id=await _version_id(
            session, ComponentType.VECTOR_STORE, chroma.KEY
        ),
        index_params={"space": "cosine"},
    )
    snapshot = await CorpusSnapshotService(session).get_or_create(
        scenario.corpus.id, [document.id for document in scenario.ready], label="v1"
    )
    build = await IndexBuildService(session).get_or_create(
        corpus_snapshot_id=snapshot.id,
        chunking_configuration_id=scenario.configuration.id,
        embedding_profile_id=embedding.id,
        vector_store_profile_id=vector_store_profile.id,
    )
    return str(build.id), str(embedding.id)


async def test_batches_are_embedded_then_upserted_into_the_build_collection(
    session, worker, fake_storage, chroma_client
) -> None:
    scenario = await build_scenario(session, ready=2, chunks_per_document=3)
    build_id, embedding_id = await _build(session, scenario, dimensions=_DIMENSIONS)

    await vector_store.prepare_index_collection(build_id)
    first = await embed.embed_batch(build_id, embedding_id, 0, 4)
    second = await embed.embed_batch(build_id, embedding_id, 4, 4)
    past_the_end = await embed.embed_batch(build_id, embedding_id, 8, 4)
    upserted = [
        await vector_store.upsert_embedding_batch(build_id, 0),
        await vector_store.upsert_embedding_batch(build_id, 4),
    ]

    assert [first.embedded_count, second.embedded_count] == [4, 2]
    assert past_the_end.embedded_count == 0
    assert upserted == [4, 2]
    assert embed.embedding_batch_key(build_id, 0) in fake_storage.objects

    build = await IndexBuildService(session).get(uuid.UUID(build_id))
    collection = chroma_client.get_collection(build.external_index_ref)
    stored = collection.get(include=["metadatas", "embeddings"])
    assert collection.count() == 6
    assert {metadata["document_id"] for metadata in stored["metadatas"]} == {
        str(document.id) for document in scenario.ready
    }
    assert {metadata["index_build_id"] for metadata in stored["metadatas"]} == {
        build_id
    }
    assert len(stored["embeddings"][0]) == _DIMENSIONS


async def test_reupserting_a_batch_does_not_duplicate_vectors(
    session, worker, chroma_client
) -> None:
    scenario = await build_scenario(session, ready=1, chunks_per_document=3)
    build_id, embedding_id = await _build(session, scenario, dimensions=_DIMENSIONS)

    await vector_store.prepare_index_collection(build_id)
    await embed.embed_batch(build_id, embedding_id, 0, 10)
    await vector_store.upsert_embedding_batch(build_id, 0)
    await vector_store.upsert_embedding_batch(build_id, 0)

    build = await IndexBuildService(session).get(uuid.UUID(build_id))
    assert chroma_client.get_collection(build.external_index_ref).count() == 3


async def test_vectors_with_the_wrong_dimensions_fail_without_retry(
    session, worker, fake_storage
) -> None:
    scenario = await build_scenario(session, ready=1)
    build_id, embedding_id = await _build(session, scenario, dimensions=8)

    with pytest.raises(ApplicationError) as raised:
        await embed.embed_batch(build_id, embedding_id, 0, 10)

    assert raised.value.non_retryable is True
    assert fake_storage.objects == {}
