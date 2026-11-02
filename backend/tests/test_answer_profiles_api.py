from __future__ import annotations

import pytest
from src.components.service import ComponentService
from tests.answer_factory import (
    ANSWER_PROFILES,
    answer_profile,
    rag_params,
    rag_simple_version,
)
from tests.pipeline_factory import make_configuration

pytestmark = pytest.mark.integration


async def _create(client, version_id, params, **extra):
    return await client.post(
        ANSWER_PROFILES,
        json={"component_version_id": str(version_id), "params": params, **extra},
    )


async def test_the_same_parameters_are_one_profile(client, session) -> None:
    version = await rag_simple_version(session)

    first = await _create(client, version.id, rag_params())
    # The defaults written out are the same configuration as leaving them to the schema.
    second = await _create(
        client, version.id, rag_params(temperature=0, max_tokens=1024)
    )

    assert first.status_code == second.status_code == 201
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert second.json()["detail"]
    assert first.json()["profile"]["id"] == second.json()["profile"]["id"]
    profile = first.json()["profile"]
    assert profile["name"] == "rag_simple@1 openai/gpt-test t=0"
    assert profile["params"]["max_tokens"] == 1024


async def test_two_prompts_are_two_profiles_with_distinct_names(
    client, session
) -> None:
    first = await answer_profile(client, session)
    second = await answer_profile(client, session, system_prompt="Be brief.")

    assert first["id"] != second["id"]
    assert first["config_hash"] != second["config_hash"]
    assert second["name"].startswith(first["name"] + " #")


async def test_a_derived_profile_lists_what_changed(client, session) -> None:
    parent = await answer_profile(client, session)
    version = await rag_simple_version(session)

    created = await _create(
        client,
        version.id,
        rag_params(system_prompt="Be brief.", temperature=0.5),
        parent_profile_id=parent["id"],
    )
    child = created.json()["profile"]
    detail = (await client.get(f"{ANSWER_PROFILES}/{child['id']}")).json()

    assert detail["parent_profile_id"] == parent["id"]
    assert detail["changed_params"] == [
        {
            "key": "system_prompt",
            "parent": "Answer from the passages only.",
            "value": "Be brief.",
        },
        {"key": "temperature", "parent": 0, "value": 0.5},
    ]
    parent_detail = (await client.get(f"{ANSWER_PROFILES}/{parent['id']}")).json()
    assert parent_detail["changed_params"] == []


async def test_only_answer_systems_have_answer_profiles(client, session) -> None:
    parsing, _ = await make_configuration(session)

    response = await _create(client, parsing.component_version_id, {})

    assert response.status_code == 422
    assert response.json()["code"] == "not_an_answer_system"


async def test_parameters_are_checked_against_the_schema(client, session) -> None:
    version = await rag_simple_version(session)

    response = await _create(client, version.id, rag_params(provider="anthropic"))

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_component_params"


async def test_an_unavailable_system_is_refused_with_its_reason(
    client, session
) -> None:
    version = await rag_simple_version(session)
    await ComponentService(session).mark_unavailable(
        version.id, "openai: OPENAI_API_KEY is not set"
    )

    response = await _create(client, version.id, rag_params())

    assert response.status_code == 422
    assert response.json()["code"] == "answer_system_not_available"
    assert "OPENAI_API_KEY" in response.json()["message"]


async def test_profiles_are_listed_by_version(client, session) -> None:
    version = await rag_simple_version(session)
    await answer_profile(client, session)
    await answer_profile(client, session, model="gpt-other")

    listed = await client.get(
        ANSWER_PROFILES, params={"component_version_id": str(version.id)}
    )

    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    assert [item["name"] for item in listed.json()["items"]] == [
        "rag_simple@1 openai/gpt-other t=0",
        "rag_simple@1 openai/gpt-test t=0",
    ]


async def test_the_worker_marks_a_system_unavailable_without_any_credential(
    session, monkeypatch
) -> None:
    from src.answering import availability

    monkeypatch.setattr(
        availability, "missing_credentials", lambda provider: f"no {provider} key"
    )
    await availability.sync_answer_system_availability(session)
    version = await rag_simple_version(session)

    assert version.is_available is False
    assert (
        version.unavailable_reason == "openai: no openai key; bedrock: no bedrock key"
    )

    # One provider with credentials is enough for the version to be offered.
    monkeypatch.setattr(
        availability,
        "missing_credentials",
        lambda provider: None if provider == "openai" else "no key",
    )
    await availability.sync_answer_system_availability(session)

    assert version.is_available is True
    assert version.unavailable_reason is None
