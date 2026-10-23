from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

RETRIEVAL_PROFILES = "/api/v1/retrieval-profiles"


async def test_the_same_retrieval_profile_under_two_names_is_one_row(client) -> None:
    body = {"top_k": 5, "strategy": "dense", "score_threshold": 0.2}

    first = await client.post(RETRIEVAL_PROFILES, json={"name": "first", **body})
    second = await client.post(RETRIEVAL_PROFILES, json={"name": "second", **body})

    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert first.json()["profile"]["id"] == second.json()["profile"]["id"]
    assert second.json()["detail"]


async def test_omitted_and_explicitly_empty_columns_hash_the_same(client) -> None:
    """The hash covers every column, so spelling out a null does not fork the profile."""
    first = await client.post(RETRIEVAL_PROFILES, json={"name": "a", "top_k": 7})
    second = await client.post(
        RETRIEVAL_PROFILES,
        json={"name": "b", "top_k": 7, "strategy": "dense", "metadata_filters": None},
    )

    assert first.json()["profile"]["id"] == second.json()["profile"]["id"]


async def test_metadata_filters_are_part_of_the_identity(client) -> None:
    first = await client.post(RETRIEVAL_PROFILES, json={"name": "a", "top_k": 5})
    second = await client.post(
        RETRIEVAL_PROFILES,
        json={"name": "b", "top_k": 5, "metadata_filters": {"lang": "it"}},
    )

    assert second.json()["created"] is True
    assert first.json()["profile"]["id"] != second.json()["profile"]["id"]


@pytest.mark.parametrize("strategy", ["sparse", "hybrid", "multi_vector"])
async def test_strategies_the_engine_does_not_apply_are_refused(
    client, strategy
) -> None:
    """Storing them would describe a retrieval nobody performs."""
    response = await client.post(
        RETRIEVAL_PROFILES, json={"name": "x", "top_k": 5, "strategy": strategy}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_retrieval_feature"
    assert response.json()["details"]["field"] == "strategy"


async def test_top_k_must_be_positive(client) -> None:
    response = await client.post(RETRIEVAL_PROFILES, json={"name": "x", "top_k": 0})

    assert response.status_code == 422


async def test_list_and_read_back(client) -> None:
    created = await client.post(RETRIEVAL_PROFILES, json={"name": "listed", "top_k": 3})
    profile_id = created.json()["profile"]["id"]

    listed = await client.get(RETRIEVAL_PROFILES)
    single = await client.get(f"{RETRIEVAL_PROFILES}/{profile_id}")
    missing = await client.get(f"{RETRIEVAL_PROFILES}/{uuid.uuid4()}")

    assert profile_id in {item["id"] for item in listed.json()["items"]}
    assert single.json()["top_k"] == 3
    assert missing.status_code == 404
