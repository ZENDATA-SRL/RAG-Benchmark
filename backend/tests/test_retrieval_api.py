from __future__ import annotations

import uuid

import chromadb
import pytest
from chromadb.config import Settings as ChromaSettings
from langchain_core.embeddings import DeterministicFakeEmbedding
from sqlalchemy import select
from src.artifacts.models import Chunk, ChunkResult
from src.components.builtin.embedder import openai_embedder
from src.components.builtin.vector_stores import chroma
from src.components.repository import ComponentRepository, ComponentVersionRepository
from src.corpora.service import CorpusSnapshotService
from src.indexes.models import IndexBuild
from src.indexes.service import IndexBuildService
from src.infrastructure.database.enums import ArtifactStatus, ComponentType
from src.pipelines.service import ProfileService
from src.retrieval.embedders import BUILTIN_EMBEDDERS
from src.retrieval.readers import BUILTIN_VECTOR_STORE_READERS
from src.retrieval.readers.chroma import ChromaVectorStoreReader
from tests.pipeline_factory import Scenario, build_scenario

from temporal.components.vector_stores.chroma import ChromaVectorStore

pytestmark = pytest.mark.integration

RETRIEVE = "/api/v1/retrieve"
_DIMENSIONS = 16


@pytest.fixture
def chroma_client():
    client = chromadb.EphemeralClient(settings=ChromaSettings(allow_reset=True))
    client.reset()
    return client


@pytest.fixture
def fake_engine(monkeypatch, chroma_client):
    """Fake only the embedder and point the reader at an in-process Chroma.

    The fake embedding is deterministic in the text, so a query equal to a chunk's text
    lands exactly on that chunk's vector.
    """
    monkeypatch.setitem(
        BUILTIN_EMBEDDERS,
        openai_embedder.KEY,
        lambda params: DeterministicFakeEmbedding(size=_DIMENSIONS),
    )
    monkeypatch.setitem(
        BUILTIN_VECTOR_STORE_READERS,
        chroma.KEY,
        lambda: ChromaVectorStoreReader(chroma_client),
    )


async def _version_id(session, component_type: ComponentType, key: str) -> uuid.UUID:
    component = await ComponentRepository(session).get_by_type_and_key(
        component_type, key
    )
    assert component is not None
    return (await ComponentVersionRepository(session).list_versions(component.id))[0].id


async def _indexed_build(
    session, scenario: Scenario, chroma_client, *, status=ArtifactStatus.READY
) -> IndexBuild:
    """An index build over the ready documents, its chunks written to Chroma."""
    profiles = ProfileService(session)
    embedding, _ = await profiles.get_or_create_embedding_profile(
        name="fake",
        component_version_id=await _version_id(
            session, ComponentType.EMBEDDER, openai_embedder.KEY
        ),
    )
    store_profile, _ = await profiles.get_or_create_vector_store_profile(
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
        vector_store_profile_id=store_profile.id,
    )
    rows = (
        await session.execute(
            select(Chunk, ChunkResult.document_id).join(
                ChunkResult, ChunkResult.id == Chunk.chunk_result_id
            )
        )
    ).all()
    writer = ChromaVectorStore(chroma_client)
    writer.ensure_collection(build.external_index_ref, {"space": "cosine"})
    fake = DeterministicFakeEmbedding(size=_DIMENSIONS)
    writer.upsert(
        build.external_index_ref,
        ids=[str(chunk.id) for chunk, _ in rows],
        embeddings=fake.embed_documents([chunk.text for chunk, _ in rows]),
        documents=[chunk.text for chunk, _ in rows],
        metadatas=[
            {"document_id": str(document_id), "ordinal": chunk.ordinal}
            for chunk, document_id in rows
        ],
        index_params={},
    )
    build.status = status
    await session.flush()
    return build


async def _retrieval_profile(client, **body) -> str:
    response = await client.post(
        "/api/v1/retrieval-profiles", json={"name": "p", "top_k": 3, **body}
    )
    assert response.status_code == 201, response.text
    return response.json()["profile"]["id"]


async def _target_chunk(session, scenario: Scenario) -> Chunk:
    """The first chunk of the first ready document."""
    stmt = (
        select(Chunk)
        .join(ChunkResult, ChunkResult.id == Chunk.chunk_result_id)
        .where(ChunkResult.document_id == scenario.ready[0].id)
        .order_by(Chunk.ordinal)
    )
    chunk = await session.scalar(stmt)
    assert chunk is not None
    return chunk


async def test_a_known_sentence_retrieves_its_chunk_first(
    client, session, fake_engine, chroma_client
) -> None:
    scenario = await build_scenario(session, ready=3, chunks_per_document=2)
    build = await _indexed_build(session, scenario, chroma_client)
    target = await _target_chunk(session, scenario)
    profile_id = await _retrieval_profile(client)

    response = await client.post(
        RETRIEVE,
        json={
            "index_build_id": str(build.id),
            "retrieval_profile_id": profile_id,
            "query": target.text,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    first = body["hits"][0]
    assert first["chunk_id"] == str(target.id)
    assert first["document_id"] == str(scenario.ready[0].id)
    assert first["filename"] == scenario.ready[0].filename
    assert first["page"] == 1
    assert first["text"] == target.text
    assert first["stage"] == "final"
    assert first["score"] == pytest.approx(1.0, abs=1e-4)
    assert [hit["rank"] for hit in body["hits"]] == [1, 2, 3]
    assert body["timings"]["total_ms"] >= 0
    assert body["corpus_id"] == scenario.corpus_id
    assert body["chunking_configuration_id"] == scenario.configuration_id


async def test_the_same_query_returns_the_same_hits(
    client, session, fake_engine, chroma_client
) -> None:
    scenario = await build_scenario(session, ready=2, chunks_per_document=2)
    build = await _indexed_build(session, scenario, chroma_client)
    profile_id = await _retrieval_profile(client)
    body = {
        "index_build_id": str(build.id),
        "retrieval_profile_id": profile_id,
        "query": "any question",
    }

    first = await client.post(RETRIEVE, json=body)
    second = await client.post(RETRIEVE, json=body)

    def ranking(response) -> list:
        return [(hit["chunk_id"], hit["score"]) for hit in response.json()["hits"]]

    assert ranking(first) == ranking(second)


async def test_the_score_threshold_drops_weak_hits(
    client, session, fake_engine, chroma_client
) -> None:
    scenario = await build_scenario(session, ready=2, chunks_per_document=2)
    build = await _indexed_build(session, scenario, chroma_client)
    target = await _target_chunk(session, scenario)
    profile_id = await _retrieval_profile(client, score_threshold=0.999)

    response = await client.post(
        RETRIEVE,
        json={
            "index_build_id": str(build.id),
            "retrieval_profile_id": profile_id,
            "query": target.text,
        },
    )

    assert [hit["chunk_id"] for hit in response.json()["hits"]] == [str(target.id)]


async def test_a_vector_whose_chunk_is_gone_comes_back_without_chunk_id(
    client, session, fake_engine, chroma_client
) -> None:
    scenario = await build_scenario(session, ready=1, chunks_per_document=1)
    build = await _indexed_build(session, scenario, chroma_client)
    target = await _target_chunk(session, scenario)
    text = target.text
    await session.delete(target)
    await session.flush()
    profile_id = await _retrieval_profile(client)

    response = await client.post(
        RETRIEVE,
        json={
            "index_build_id": str(build.id),
            "retrieval_profile_id": profile_id,
            "query": text,
        },
    )

    assert response.status_code == 200
    first = response.json()["hits"][0]
    assert first["chunk_id"] is None
    assert first["text"] == text
    assert first["document_id"] == str(scenario.ready[0].id)


@pytest.mark.parametrize("status", [ArtifactStatus.PENDING, ArtifactStatus.RUNNING])
async def test_a_build_that_is_not_ready_is_refused(
    client, session, fake_engine, chroma_client, status
) -> None:
    scenario = await build_scenario(session, ready=1)
    build = await _indexed_build(session, scenario, chroma_client, status=status)
    profile_id = await _retrieval_profile(client)

    response = await client.post(
        RETRIEVE,
        json={
            "index_build_id": str(build.id),
            "retrieval_profile_id": profile_id,
            "query": "anything",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "index_build_not_ready"


async def test_an_unknown_build_is_not_found(client, fake_engine) -> None:
    profile_id = await _retrieval_profile(client)

    response = await client.post(
        RETRIEVE,
        json={
            "index_build_id": str(uuid.uuid4()),
            "retrieval_profile_id": profile_id,
            "query": "anything",
        },
    )

    assert response.status_code == 404


async def test_a_vector_store_failure_is_reported_as_a_bad_gateway(
    client, session, fake_engine, chroma_client, monkeypatch
) -> None:
    scenario = await build_scenario(session, ready=1)
    build = await _indexed_build(session, scenario, chroma_client)
    profile_id = await _retrieval_profile(client)
    chroma_client.delete_collection(build.external_index_ref)

    response = await client.post(
        RETRIEVE,
        json={
            "index_build_id": str(build.id),
            "retrieval_profile_id": profile_id,
            "query": "anything",
        },
    )

    assert response.status_code == 502
    assert response.json()["details"]["stage"] == "vector store"
