from __future__ import annotations

import uuid

import pytest
from src.components.builtin.chunkers import markdown, recursive
from src.components.builtin.parsers import pdfplumber, pypdf
from src.components.registry_seed import seed_builtin_components

pytestmark = pytest.mark.integration

COMPONENTS_URL = "/api/v1/components"


async def test_health_is_open(client) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_list_components_exposes_the_builtins_with_their_schema(client, session) -> None:
    """The acceptance of the DoD: `GET /api/v1/components` feeds the dynamic forms (RT-U01)."""
    await seed_builtin_components(session)

    response = await client.get(COMPONENTS_URL)

    assert response.status_code == 200
    body = response.json()
    by_key = {component["key"]: component for component in body}
    assert set(by_key) == {pypdf.KEY, pdfplumber.KEY, recursive.KEY, markdown.KEY}

    chunker = by_key[recursive.KEY]
    assert chunker["type"] == "chunker"
    assert len(chunker["versions"]) == 1
    version = chunker["versions"][0]
    assert version["runtime"] == "builtin"
    assert version["capabilities"]["scope"] == "document"
    assert set(version["params_schema"]["properties"]) == {
        "chunk_size",
        "overlap",
        "separators",
        "strip_headers_footers",
    }


async def test_list_components_filters_by_type(client, session) -> None:
    await seed_builtin_components(session)

    response = await client.get(COMPONENTS_URL, params={"type": "parser"})

    assert response.status_code == 200
    assert [component["key"] for component in response.json()] == sorted(
        [pdfplumber.KEY, pypdf.KEY]
    )


async def test_list_versions_of_a_component(client, session) -> None:
    await seed_builtin_components(session)
    component_id = (await client.get(COMPONENTS_URL, params={"type": "parser"})).json()[0]["id"]

    response = await client.get(f"{COMPONENTS_URL}/{component_id}/versions")

    assert response.status_code == 200
    assert [version["version"] for version in response.json()] == [pypdf.VERSION]


async def test_register_component_twice_returns_the_same_id(client) -> None:
    payload = {"type": "parser", "key": pypdf.KEY, "display_name": "PyPDF"}

    first = await client.post(COMPONENTS_URL, json=payload)
    second = await client.post(COMPONENTS_URL, json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_register_version_over_http_runtime_is_a_domain_error(client) -> None:
    """A domain error must serialise as `{code, message, details}` and not as a 500."""
    component_id = (
        await client.post(
            COMPONENTS_URL, json={"type": "parser", "key": pypdf.KEY, "display_name": "PyPDF"}
        )
    ).json()["id"]

    response = await client.post(
        f"{COMPONENTS_URL}/{component_id}/versions",
        json={"version": "2", "runtime": "http", "endpoint": "http://parser.internal"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "unsupported_runtime"
    assert body["details"]["runtime"] == "http"
    assert body["details"]["supported"] == ["builtin"]
    assert "message" in body


async def test_unknown_component_returns_the_uniform_404(client) -> None:
    response = await client.get(f"{COMPONENTS_URL}/{uuid.uuid4()}/versions")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "component_not_found"
    assert set(body) == {"code", "message", "details"}


async def test_invalid_params_schema_returns_422_with_the_reason(client) -> None:
    component_id = (
        await client.post(
            COMPONENTS_URL, json={"type": "parser", "key": pypdf.KEY, "display_name": "PyPDF"}
        )
    ).json()["id"]

    response = await client.post(
        f"{COMPONENTS_URL}/{component_id}/versions",
        json={"version": "1", "params_schema": {"type": "nonsense"}},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_params_schema"


async def test_mark_version_unavailable_then_available(client, session) -> None:
    await seed_builtin_components(session)
    component = (await client.get(COMPONENTS_URL, params={"type": "parser"})).json()[0]
    version_id = component["versions"][0]["id"]

    unavailable = await client.post(
        f"{COMPONENTS_URL}/versions/{version_id}/unavailable",
        json={"reason": "missing credential"},
    )
    assert unavailable.status_code == 200
    assert unavailable.json()["is_available"] is False
    assert unavailable.json()["unavailable_reason"] == "missing credential"

    filtered = await client.get(COMPONENTS_URL, params={"type": "parser", "only_available": True})
    assert filtered.json()[0]["versions"] == []

    restored = await client.post(f"{COMPONENTS_URL}/versions/{version_id}/available")
    assert restored.status_code == 200
    assert restored.json()["is_available"] is True


async def test_response_carries_a_request_id(client) -> None:
    """The id is echoed so a failure reported from the UI is greppable in the logs."""
    response = await client.get("/health")

    assert response.headers["X-Request-ID"]
