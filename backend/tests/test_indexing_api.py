from __future__ import annotations

import uuid

import pytest
from src.components.builtin.embedder import openai_embedder
from src.components.builtin.vector_stores import chroma
from src.components.repository import ComponentRepository, ComponentVersionRepository
from src.corpora.models import CorpusDocument
from src.corpora.repository import CorpusSnapshotRepository
from src.corpora.service import CorpusSnapshotService
from src.indexes.repository import IndexBuildRepository
from src.infrastructure.database.enums import ComponentType, DocumentStatus
from src.infrastructure.temporal.workflow_ids import (
    INDEX_CORPUS_WORKFLOW,
    materialize_workflow_id,
    materialize_workflow_id_for_composition,
)
from tests.pipeline_factory import Scenario, build_scenario, make_document

pytestmark = pytest.mark.integration

CORPORA_URL = "/api/v1/corpora"
EMBEDDING_PROFILES = "/api/v1/embedding-profiles"
VECTOR_STORE_PROFILES = "/api/v1/vector-store-profiles"
INDEX_BUILDS = "/api/v1/index-builds"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


async def _version_id(session, component_type: ComponentType, key: str) -> str:
    """Id of the seeded version of a builtin; `build_scenario` has seeded the registry."""
    component = await ComponentRepository(session).get_by_type_and_key(
        component_type, key
    )
    assert component is not None
    versions = await ComponentVersionRepository(session).list_versions(component.id)
    return str(versions[0].id)


async def _embedding_profile(client, session, **overrides) -> dict:
    payload = {
        "name": "small",
        "component_version_id": await _version_id(
            session, ComponentType.EMBEDDER, openai_embedder.KEY
        ),
        "modality": "text",
        "dimensions": 1536,
        "params": {"model_name": "text-embedding-3-small"},
        **overrides,
    }
    response = await client.post(EMBEDDING_PROFILES, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["profile"]


async def _vector_store_profile(client, session, **overrides) -> dict:
    payload = {
        "name": "chroma cosine",
        "component_version_id": await _version_id(
            session, ComponentType.VECTOR_STORE, chroma.KEY
        ),
        "index_params": {"space": "cosine"},
        **overrides,
    }
    response = await client.post(VECTOR_STORE_PROFILES, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["profile"]


async def _snapshot(client, scenario: Scenario, **payload) -> dict:
    response = await client.post(
        f"{CORPORA_URL}/{scenario.corpus_id}/snapshots",
        json={"label": "v1", **payload},
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------------------
# Snapshots
# --------------------------------------------------------------------------------------


async def test_snapshot_without_ids_freezes_the_stored_documents(
    client, session
) -> None:
    """A document whose acquisition failed cannot be parsed, so it is left out."""
    scenario = await build_scenario(session, ready=2)
    broken = await make_document(session, filename="broken.pdf")
    broken.status = DocumentStatus.FAILED
    session.add(CorpusDocument(corpus_id=scenario.corpus.id, document_id=broken.id))
    await session.flush()

    body = await _snapshot(client, scenario)

    assert body["created"] is True
    assert body["detail"] is None
    assert body["snapshot"]["document_count"] == 2
    listed = await client.get(
        f"{CORPORA_URL}/{scenario.corpus_id}/snapshots/{body['snapshot']['id']}/documents"
    )
    assert {document["id"] for document in listed.json()["items"]} == {
        str(document.id) for document in scenario.ready
    }


async def test_same_composition_returns_the_existing_snapshot(client, session) -> None:
    scenario = await build_scenario(session, ready=2)
    ids = [str(document.id) for document in scenario.ready]

    first = await _snapshot(client, scenario, document_ids=ids)
    second = await _snapshot(
        client, scenario, label="renamed", document_ids=list(reversed(ids))
    )

    assert second["created"] is False
    assert second["detail"] is not None
    assert second["snapshot"]["id"] == first["snapshot"]["id"]
    assert second["snapshot"]["label"] == "v1"


async def test_snapshot_rejects_documents_outside_the_corpus(client, session) -> None:
    scenario = await build_scenario(session, ready=1)
    stranger = await make_document(session, filename="stranger.pdf")

    response = await client.post(
        f"{CORPORA_URL}/{scenario.corpus_id}/snapshots",
        json={"label": "v1", "document_ids": [str(stranger.id)]},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "documents_not_in_corpus"


async def test_snapshot_of_an_unknown_corpus_is_404(client) -> None:
    response = await client.post(
        f"{CORPORA_URL}/{UNKNOWN_ID}/snapshots", json={"label": "v1"}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "corpus_not_found"


async def test_snapshot_of_an_empty_corpus_is_rejected(client) -> None:
    corpus_id = (await client.post(CORPORA_URL, json={"name": "Vuoto"})).json()["id"]

    response = await client.post(
        f"{CORPORA_URL}/{corpus_id}/snapshots", json={"label": "v1"}
    )

    assert response.status_code == 422


async def test_snapshots_are_listed_and_read_per_corpus(client, session) -> None:
    scenario = await build_scenario(session, ready=2)
    first = await _snapshot(client, scenario, document_ids=[str(scenario.ready[0].id)])
    await _snapshot(client, scenario, document_ids=[str(scenario.ready[1].id)])

    listed = await client.get(f"{CORPORA_URL}/{scenario.corpus_id}/snapshots")
    fetched = await client.get(
        f"{CORPORA_URL}/{scenario.corpus_id}/snapshots/{first['snapshot']['id']}"
    )
    other_corpus = (await client.post(CORPORA_URL, json={"name": "Altro"})).json()["id"]
    misplaced = await client.get(
        f"{CORPORA_URL}/{other_corpus}/snapshots/{first['snapshot']['id']}"
    )

    assert listed.json()["total"] == 2
    assert fetched.json() == first["snapshot"]
    assert misplaced.status_code == 404
    assert misplaced.json()["code"] == "corpus_snapshot_not_found"


# --------------------------------------------------------------------------------------
# Profiles
# --------------------------------------------------------------------------------------


async def test_vector_store_profile_is_created_deduplicated_and_read(
    client, session
) -> None:
    await build_scenario(session)
    created = await _vector_store_profile(client, session)

    again = await client.post(
        VECTOR_STORE_PROFILES,
        json={
            "name": "another name",
            "component_version_id": created["component_version_id"],
            "index_params": {"space": "cosine"},
        },
    )
    fetched = await client.get(f"{VECTOR_STORE_PROFILES}/{created['id']}")
    listed = await client.get(VECTOR_STORE_PROFILES)

    assert again.json()["created"] is False
    assert again.json()["profile"]["id"] == created["id"]
    assert fetched.json() == created
    assert listed.json()["total"] == 1


async def test_vector_store_profile_rejects_params_outside_the_schema(
    client, session
) -> None:
    await build_scenario(session)

    response = await client.post(
        VECTOR_STORE_PROFILES,
        json={
            "name": "bad",
            "component_version_id": await _version_id(
                session, ComponentType.VECTOR_STORE, chroma.KEY
            ),
            "index_params": {"space": "manhattan"},
        },
    )

    assert response.status_code == 422


async def test_embedding_profile_is_read_by_id(client, session) -> None:
    await build_scenario(session)
    created = await _embedding_profile(client, session)

    fetched = await client.get(f"{EMBEDDING_PROFILES}/{created['id']}")
    missing = await client.get(f"{EMBEDDING_PROFILES}/{UNKNOWN_ID}")

    assert fetched.json() == created
    assert missing.status_code == 404


# --------------------------------------------------------------------------------------
# Index builds
# --------------------------------------------------------------------------------------


async def _index_build(client, session, scenario: Scenario) -> dict:
    snapshot = (await _snapshot(client, scenario))["snapshot"]
    embedding = await _embedding_profile(client, session)
    vector_store = await _vector_store_profile(client, session)
    response = await client.post(
        INDEX_BUILDS,
        json={
            "corpus_snapshot_id": snapshot["id"],
            "chunking_configuration_id": scenario.configuration_id,
            "embedding_profile_id": embedding["id"],
            "vector_store_profile_id": vector_store["id"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["index_build"]


async def test_index_build_is_created_read_and_started_over_http(
    client, session, fake_workflows
) -> None:
    """The whole chain is reachable through the API: snapshot, profiles, build, start."""
    scenario = await build_scenario(session, ready=2, chunks_per_document=3)
    build = await _index_build(client, session, scenario)

    fetched = await client.get(f"{INDEX_BUILDS}/{build['id']}")
    started = await client.post(f"{INDEX_BUILDS}/{build['id']}/start")

    assert fetched.status_code == 200
    assert fetched.json()["chunk_count"] == 6
    assert fetched.json()["status"] == "pending"
    assert started.status_code == 202
    assert fake_workflows.started[0].workflow == INDEX_CORPUS_WORKFLOW
    assert fake_workflows.started[0].arg == build["id"]


async def test_index_builds_are_listed_by_snapshot(client, session) -> None:
    scenario = await build_scenario(session, ready=1)
    build = await _index_build(client, session, scenario)

    by_snapshot = await client.get(
        INDEX_BUILDS, params={"corpus_snapshot_id": build["corpus_snapshot_id"]}
    )
    other = await client.get(INDEX_BUILDS, params={"corpus_snapshot_id": UNKNOWN_ID})

    assert [item["id"] for item in by_snapshot.json()["items"]] == [build["id"]]
    assert other.json()["total"] == 0


async def test_unknown_index_build_is_404(client) -> None:
    response = await client.get(f"{INDEX_BUILDS}/{UNKNOWN_ID}")

    assert response.status_code == 404
    assert response.json()["code"] == "index_build_not_found"


# --------------------------------------------------------------------------------------
# Queries the worker relies on
# --------------------------------------------------------------------------------------


async def test_build_chunks_carry_their_document(client, session) -> None:
    scenario = await build_scenario(session, ready=2, chunks_per_document=2)
    build = await _index_build(client, session, scenario)

    rows = await IndexBuildRepository(session).list_chunks(uuid.UUID(build["id"]))

    assert len(rows) == 4
    assert {document_id for _, document_id in rows} == {
        document.id for document in scenario.ready
    }


async def test_snapshot_document_ids_are_paged_without_overlap(session) -> None:
    scenario = await build_scenario(session, ready=5)
    snapshot = await CorpusSnapshotService(session).get_or_create(
        scenario.corpus.id, [document.id for document in scenario.ready], label="v1"
    )
    repository = CorpusSnapshotRepository(session)

    pages = [
        await repository.list_snapshot_document_ids(snapshot.id, limit=2, offset=offset)
        for offset in (0, 2, 4)
    ]

    flattened = [document_id for page in pages for document_id in page]
    assert [len(page) for page in pages] == [2, 2, 1]
    assert set(flattened) == {document.id for document in scenario.ready}


async def test_snapshot_hash_gives_the_same_materialisation_id(session) -> None:
    """An index build and a launch by list must collide on the same workflow id."""
    scenario = await build_scenario(session, ready=3)
    ids = [document.id for document in scenario.ready]
    snapshot = await CorpusSnapshotService(session).get_or_create(
        scenario.corpus.id, ids, label="v1"
    )

    assert materialize_workflow_id_for_composition(
        scenario.configuration.id, snapshot.composition_hash
    ) == materialize_workflow_id(scenario.configuration.id, ids)
