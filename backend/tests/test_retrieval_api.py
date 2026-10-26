from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from src.artifacts.models import Chunk, ChunkResult
from src.infrastructure.database.enums import ArtifactStatus
from tests.pipeline_factory import Scenario, build_scenario
from tests.retrieval_factory import indexed_build

pytestmark = pytest.mark.integration

RETRIEVE = "/api/v1/retrieve"


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
    build = await indexed_build(session, scenario, chroma_client)
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
    build = await indexed_build(session, scenario, chroma_client)
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
    build = await indexed_build(session, scenario, chroma_client)
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
    build = await indexed_build(session, scenario, chroma_client)
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
    build = await indexed_build(session, scenario, chroma_client, status=status)
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
    build = await indexed_build(session, scenario, chroma_client)
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
