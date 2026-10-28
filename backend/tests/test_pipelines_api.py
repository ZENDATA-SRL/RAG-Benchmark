from __future__ import annotations

import json
import uuid

import pytest
from src.components.builtin.chunkers import recursive
from src.components.builtin.parsers import pypdf
from src.components.registry_seed import seed_builtin_components
from src.components.repository import ComponentRepository, ComponentVersionRepository
from src.infrastructure.database.enums import ComponentType
from src.infrastructure.storage.base import parse_key
from tests.pipeline_factory import (
    build_scenario,
    make_configuration,
    make_document,
    materialise,
)

pytestmark = pytest.mark.integration

PARSING_PROFILES = "/api/v1/parsing-profiles"
CHUNKING_PROFILES = "/api/v1/chunking-profiles"
CONFIGURATIONS = "/api/v1/chunking-configurations"


async def _version_ids(session) -> tuple[str, str]:
    """Ids of the seeded pypdf and recursive component versions."""
    await seed_builtin_components(session)
    components = ComponentRepository(session)
    versions = ComponentVersionRepository(session)
    parser = await components.get_by_type_and_key(ComponentType.PARSER, pypdf.KEY)
    chunker = await components.get_by_type_and_key(ComponentType.CHUNKER, recursive.KEY)
    assert parser is not None and chunker is not None
    return (
        str((await versions.list_versions(parser.id))[0].id),
        str((await versions.list_versions(chunker.id))[0].id),
    )


async def _compose(client, session, *, chunk_size: int = 500) -> dict:
    parser_version, chunker_version = await _version_ids(session)
    response = await client.post(
        f"{CONFIGURATIONS}/compose",
        json={
            "parsing_component_version_id": parser_version,
            "chunking_component_version_id": chunker_version,
            "chunking_strategy": recursive.STRATEGY,
            "chunk_size": chunk_size,
            "overlap": 50,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------------------
# profiles
# --------------------------------------------------------------------------------------


async def test_creating_the_same_profile_twice_returns_one_row(client, session) -> None:
    """Dedup is on the parameters, and the response admits it."""
    parser_version, _ = await _version_ids(session)
    payload = {"component_version_id": parser_version, "params": {}}

    first = await client.post(PARSING_PROFILES, json=payload)
    second = await client.post(PARSING_PROFILES, json=payload)

    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert first.json()["profile"]["id"] == second.json()["profile"]["id"]
    assert first.json()["profile"]["name"] == "pypdf@1"
    assert second.json()["detail"]


async def test_profiles_that_would_read_the_same_get_a_hash_suffix(
    client, session
) -> None:
    """A parameter the name does not show must not leave two profiles indistinguishable."""
    parser_version, _ = await _version_ids(session)

    plain = await client.post(
        PARSING_PROFILES,
        json={"component_version_id": parser_version, "params": {}},
    )
    images = await client.post(
        PARSING_PROFILES,
        json={
            "component_version_id": parser_version,
            "params": {"extract_images": True},
        },
    )

    assert plain.json()["profile"]["name"] == "pypdf@1"
    other = images.json()["profile"]
    assert other["name"] == f"pypdf@1 #{other['config_hash'][:6]}"


async def test_params_outside_the_schema_are_refused_with_the_field_path(
    client, session
) -> None:
    """Server-side validation: without it the UI validation is only cosmetic."""
    parser_version, _ = await _version_ids(session)

    response = await client.post(
        PARSING_PROFILES,
        json={
            "name": "bad",
            "component_version_id": parser_version,
            "params": {"extract_images": "yes please"},
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_component_params"
    assert "field_path" in response.json()["details"]


async def test_chunking_profile_params_are_validated_too(client, session) -> None:
    _, chunker_version = await _version_ids(session)

    response = await client.post(
        CHUNKING_PROFILES,
        json={
            "name": "nonsense",
            "component_version_id": chunker_version,
            "strategy": recursive.STRATEGY,
            "params": {"separators": [1, 2]},
            "chunk_size": 500,
            "overlap": 50,
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_component_params"


async def test_unknown_component_version_is_a_404_not_a_500(client) -> None:
    response = await client.post(
        PARSING_PROFILES,
        json={"name": "x", "component_version_id": str(uuid.uuid4()), "params": {}},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "component_version_not_found"


async def test_profiles_are_listed_and_readable_by_id(client, session) -> None:
    parser_version, _ = await _version_ids(session)
    created = (
        await client.post(
            PARSING_PROFILES,
            json={
                "name": "pypdf",
                "component_version_id": parser_version,
                "params": {},
            },
        )
    ).json()["profile"]

    listing = await client.get(PARSING_PROFILES)
    detail = await client.get(f"{PARSING_PROFILES}/{created['id']}")

    assert listing.json()["total"] == 1
    assert detail.status_code == 200
    assert detail.json()["config_hash"] == created["config_hash"]


async def test_reading_an_unknown_profile_is_a_404(client) -> None:
    response = await client.get(f"{PARSING_PROFILES}/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == "profile_not_found"
    assert response.json()["details"]["kind"] == "parsing"


# --------------------------------------------------------------------------------------
# 4.2 configurations
# --------------------------------------------------------------------------------------


async def test_compose_creates_both_profiles_and_the_configuration_at_once(
    client, session
) -> None:
    body = await _compose(client, session)

    assert body["created"] is True
    assert body["parsing_profile_created"] is True
    assert body["chunking_profile_created"] is True
    configuration = body["configuration"]
    assert configuration["parsing_profile"]["name"] == "pypdf@1"
    assert configuration["chunking_profile"]["name"] == "recursive@1 500/50"
    assert configuration["name"] == "pypdf@1 → recursive@1 500/50"


async def test_composing_twice_reuses_every_row(client, session) -> None:
    first = await _compose(client, session)
    second = await _compose(client, session)

    assert second["created"] is False
    assert second["parsing_profile_created"] is False
    assert second["configuration"]["id"] == first["configuration"]["id"]


async def test_configurations_are_listed_with_their_profiles_expanded(
    client, session
) -> None:
    """The UI must be able to label a row without three extra calls."""
    await _compose(client, session)

    response = await client.get(CONFIGURATIONS)

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["parsing_profile"]["config_hash"]
    assert item["chunking_profile"]["strategy"] == recursive.STRATEGY


async def test_creating_a_configuration_from_existing_profile_ids(
    client, session
) -> None:
    parsing_profile, configuration = await make_configuration(session)

    response = await client.post(
        CONFIGURATIONS,
        json={
            "parsing_profile_id": str(configuration.parsing_profile_id),
            "chunking_profile_id": str(configuration.chunking_profile_id),
        },
    )

    assert response.status_code == 201
    assert response.json()["created"] is False
    assert response.json()["configuration"]["id"] == str(configuration.id)
    assert response.json()["configuration"]["parsing_profile"]["id"] == str(
        parsing_profile.id
    )


async def test_configuration_from_an_unknown_profile_is_a_404(client, session) -> None:
    _, configuration = await make_configuration(session)

    response = await client.post(
        CONFIGURATIONS,
        json={
            "parsing_profile_id": str(uuid.uuid4()),
            "chunking_profile_id": str(configuration.chunking_profile_id),
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "profile_not_found"
    assert response.json()["details"]["kind"] == "parsing"


async def test_coverage_of_a_half_materialised_corpus_sums_to_the_corpus_size(
    client, session
) -> None:
    """Three counts, and their sum is the size of the corpus."""
    scenario = await build_scenario(session, ready=2, failed=1, missing=2)

    response = await client.get(
        f"{CONFIGURATIONS}/{scenario.configuration_id}/coverage",
        params={"corpus_id": scenario.corpus_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["ready"], body["failed"], body["missing"]) == (2, 1, 2)
    assert body["ready"] + body["failed"] + body["missing"] == body["total"] == 5
    assert body["is_complete"] is False


async def test_coverage_of_a_fully_materialised_corpus_is_complete(
    client, session
) -> None:
    scenario = await build_scenario(session, ready=3)

    body = (
        await client.get(
            f"{CONFIGURATIONS}/{scenario.configuration_id}/coverage",
            params={"corpus_id": scenario.corpus_id},
        )
    ).json()

    assert body["is_complete"] is True
    assert body["missing"] == 0


async def test_coverage_of_an_empty_corpus_is_not_complete(client, session) -> None:
    """Zero of zero is a corpus with nothing in it, and calling that "done" would mislead."""
    scenario = await build_scenario(session)

    body = (
        await client.get(
            f"{CONFIGURATIONS}/{scenario.configuration_id}/coverage",
            params={"corpus_id": scenario.corpus_id},
        )
    ).json()

    assert body["total"] == 0
    assert body["is_complete"] is False


# --------------------------------------------------------------------------------------
# 4.4 chunk inspection
# --------------------------------------------------------------------------------------


async def test_chunks_are_returned_in_ordinal_order_and_paginated(
    client, session
) -> None:
    scenario = await build_scenario(session, ready=1, chunks_per_document=5)
    document_id = scenario.ready[0].id

    first = await client.get(
        f"/api/v1/documents/{document_id}/chunks",
        params={"chunking_configuration_id": scenario.configuration_id, "limit": 2},
    )
    second = await client.get(
        f"/api/v1/documents/{document_id}/chunks",
        params={
            "chunking_configuration_id": scenario.configuration_id,
            "limit": 2,
            "offset": 2,
        },
    )

    assert first.status_code == 200
    assert first.json()["total"] == 5
    assert [chunk["ordinal"] for chunk in first.json()["items"]] == [0, 1]
    assert [chunk["ordinal"] for chunk in second.json()["items"]] == [2, 3]
    assert first.json()["items"][0]["metadata"]["page"] == 1
    assert first.json()["chunk_result"]["status"] == "ready"
    assert first.json()["chunk_result"]["chunk_count"] == 5


async def test_the_same_document_under_two_configurations_yields_different_chunks(
    client, session
) -> None:
    """Two configurations over one document, both inspectable."""
    small = await build_scenario(session, ready=1, chunks_per_document=3)
    document = small.ready[0]
    parsing_profile, big = await make_configuration(session, chunk_size=900)
    await materialise(session, document, parsing_profile, big, chunk_count=6)

    first = (
        await client.get(
            f"/api/v1/documents/{document.id}/chunks",
            params={"chunking_configuration_id": small.configuration_id},
        )
    ).json()
    second = (
        await client.get(
            f"/api/v1/documents/{document.id}/chunks",
            params={"chunking_configuration_id": str(big.id)},
        )
    ).json()

    assert small.configuration.id != big.id
    assert (first["total"], second["total"]) == (3, 6)
    assert [c["text"] for c in first["items"]] != [c["text"] for c in second["items"]]


async def test_comparing_two_configurations_returns_both_sides(client, session) -> None:
    small = await build_scenario(session, ready=1, chunks_per_document=3)
    document = small.ready[0]
    parsing_profile, big = await make_configuration(session, chunk_size=900)
    await materialise(session, document, parsing_profile, big, chunk_count=6)

    response = await client.get(
        f"/api/v1/documents/{document.id}/chunks/compare",
        params={"configurations": f"{small.configuration.id},{big.id}"},
    )

    assert response.status_code == 200
    assert [len(side["chunks"]) for side in response.json()["sides"]] == [3, 6]


async def test_comparing_a_malformed_configuration_list_is_a_422(
    client, session
) -> None:
    scenario = await build_scenario(session, ready=1)

    response = await client.get(
        f"/api/v1/documents/{scenario.ready[0].id}/chunks/compare",
        params={"configurations": "not-a-uuid"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_configuration_list"


async def test_chunk_state_is_read_from_the_artefact_not_the_document(
    client, session
) -> None:
    """Parsing and chunking state belongs to the artefact, so the API reads it there."""
    scenario = await build_scenario(session, failed=1)

    response = await client.get(
        "/api/v1/chunk-results",
        params={
            "document_id": str(scenario.failed[0].id),
            "chunking_configuration_id": scenario.configuration_id,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error"] == "boom"


async def test_a_never_materialised_pair_is_a_404_not_an_empty_list(
    client, session
) -> None:
    """An empty page would claim the document was chunked into nothing, which is a lie."""
    scenario = await build_scenario(session, ready=1)
    other = await make_document(session)

    response = await client.get(
        f"/api/v1/documents/{other.id}/chunks",
        params={"chunking_configuration_id": scenario.configuration_id},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "chunk_result_not_found"


async def test_a_single_chunk_is_readable_by_id(client, session) -> None:
    scenario = await build_scenario(session, ready=1, chunks_per_document=2)
    chunks = (
        await client.get(
            f"/api/v1/documents/{scenario.ready[0].id}/chunks",
            params={"chunking_configuration_id": scenario.configuration_id},
        )
    ).json()["items"]

    response = await client.get(f"/api/v1/chunks/{chunks[1]['id']}")

    assert response.status_code == 200
    assert response.json()["ordinal"] == 1


async def test_an_unknown_chunk_is_a_404(client) -> None:
    response = await client.get(f"/api/v1/chunks/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == "chunk_not_found"


# --------------------------------------------------------------------------------------
# parse preview
# --------------------------------------------------------------------------------------


async def test_parse_preview_returns_the_text_of_the_requested_page(
    client, session, fake_storage
) -> None:
    """The diagnostic view for "the chunking looks odd", which usually means the parse does."""
    scenario = await build_scenario(session, ready=1)
    document = scenario.ready[0]
    key = parse_key(scenario.parsing_profile.config_hash, document.content_hash)
    fake_storage.objects[key] = json.dumps(
        {"pages": [{"page": n, "text": f"text of page {n}"} for n in range(1, 6)]}
    ).encode()

    response = await client.get(
        f"/api/v1/documents/{document.id}/parse",
        params={
            "parsing_profile_id": str(scenario.parsing_profile.id),
            "limit": 1,
            "offset": 2,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["items"] == [{"page": 3, "text": "text of page 3"}]


async def test_parse_preview_of_an_unparsed_document_is_a_404(client, session) -> None:
    scenario = await build_scenario(session, ready=1)
    other = await make_document(session)

    response = await client.get(
        f"/api/v1/documents/{other.id}/parse",
        params={"parsing_profile_id": str(scenario.parsing_profile.id)},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "parsing_result_not_found"
