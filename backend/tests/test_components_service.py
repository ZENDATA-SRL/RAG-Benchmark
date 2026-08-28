from __future__ import annotations

import uuid

import pytest
from src.components.builtin.chunkers import recursive
from src.components.builtin.parsers import pypdf
from src.components.exceptions import (
    ComponentVersionNotFoundError,
    InvalidComponentParamsError,
    InvalidParamsSchemaError,
    UnknownBuiltinError,
    UnsupportedRuntimeError,
)
from src.components.registry_seed import seed_builtin_components
from src.components.service import ComponentService
from src.infrastructure.database.enums import ComponentType, RuntimeType

pytestmark = pytest.mark.integration


async def test_register_component_is_idempotent(session) -> None:
    """Registering twice must reuse the row, or the startup seed would duplicate."""
    service = ComponentService(session)

    first = await service.register_component(ComponentType.PARSER, pypdf.KEY, "PyPDF")
    second = await service.register_component(ComponentType.PARSER, pypdf.KEY, "Renamed")

    assert first.id == second.id


async def test_register_version_is_idempotent(session) -> None:
    service = ComponentService(session)
    component = await service.register_component(ComponentType.PARSER, pypdf.KEY, "PyPDF")

    first = await service.register_version(
        component_id=component.id, version="1", params_schema=pypdf.PARAMS_SCHEMA
    )
    second = await service.register_version(
        component_id=component.id, version="1", params_schema=pypdf.PARAMS_SCHEMA
    )

    assert first.id == second.id


async def test_seed_twice_yields_two_components_with_one_version(session) -> None:
    """The acceptance of 1.6: two consecutive startups leave exactly two components."""
    await seed_builtin_components(session)
    await seed_builtin_components(session)

    components = await ComponentService(session).list_components()
    keys = sorted(component.key for component in components)
    assert keys == sorted([pypdf.KEY, recursive.KEY])

    for component in components:
        versions = await ComponentService(session).list_versions(component.id)
        assert len(versions) == 1


async def test_http_runtime_is_rejected(session) -> None:
    """`http` is modelled but has no client, so it must fail loudly."""
    service = ComponentService(session)
    component = await service.register_component(ComponentType.PARSER, pypdf.KEY, "PyPDF")

    with pytest.raises(UnsupportedRuntimeError):
        await service.register_version(
            component_id=component.id,
            version="2",
            runtime=RuntimeType.HTTP,
            endpoint="http://parser.internal",
        )


async def test_builtin_without_implementation_is_rejected(session) -> None:
    """A key nobody declared must not become a registry row."""
    service = ComponentService(session)
    component = await service.register_component(
        ComponentType.PARSER, "not-in-repository", "Ghost"
    )

    with pytest.raises(UnknownBuiltinError):
        await service.register_version(component_id=component.id, version="1")


async def test_invalid_params_schema_is_rejected(session) -> None:
    """A broken schema must fail at registration, not as a broken form later."""
    service = ComponentService(session)
    component = await service.register_component(ComponentType.PARSER, pypdf.KEY, "PyPDF")

    with pytest.raises(InvalidParamsSchemaError):
        await service.register_version(
            component_id=component.id,
            version="1",
            params_schema={"type": "not-a-json-schema-type"},
        )


async def test_validate_params_accepts_conforming_params(session) -> None:
    service = ComponentService(session)
    component = await service.register_component(
        ComponentType.CHUNKER, recursive.KEY, recursive.DISPLAY_NAME
    )
    version = await service.register_version(
        component_id=component.id,
        version="1",
        params_schema=recursive.PARAMS_SCHEMA,
        capabilities=recursive.CAPABILITIES,
    )

    await service.validate_params(version.id, {"chunk_size": 800, "overlap": 100})


async def test_validate_params_reports_the_invalid_field_path(session) -> None:
    """The field path is what lets the UI mark the offending input."""
    service = ComponentService(session)
    component = await service.register_component(
        ComponentType.CHUNKER, recursive.KEY, recursive.DISPLAY_NAME
    )
    version = await service.register_version(
        component_id=component.id, version="1", params_schema=recursive.PARAMS_SCHEMA
    )

    with pytest.raises(InvalidComponentParamsError) as raised:
        await service.validate_params(version.id, {"chunk_size": "big", "overlap": 0})

    assert raised.value.field_path == "chunk_size"
    assert raised.value.status_code == 422


async def test_validate_params_rejects_unknown_parameter(session) -> None:
    service = ComponentService(session)
    component = await service.register_component(
        ComponentType.CHUNKER, recursive.KEY, recursive.DISPLAY_NAME
    )
    version = await service.register_version(
        component_id=component.id, version="1", params_schema=recursive.PARAMS_SCHEMA
    )

    with pytest.raises(InvalidComponentParamsError):
        await service.validate_params(
            version.id, {"chunk_size": 800, "overlap": 0, "nope": True}
        )


async def test_validate_params_on_missing_version(session) -> None:
    with pytest.raises(ComponentVersionNotFoundError):
        await ComponentService(session).validate_params(uuid.uuid4(), {})


async def test_mark_unavailable_keeps_the_row_and_the_reason(session) -> None:
    """Excluding a component is a state change with a motive, not a deletion."""
    service = ComponentService(session)
    component = await service.register_component(ComponentType.PARSER, pypdf.KEY, "PyPDF")
    version = await service.register_version(component_id=component.id, version="1")

    updated = await service.mark_unavailable(version.id, "missing credential")

    assert updated.id == version.id
    assert updated.is_available is False
    assert updated.unavailable_reason == "missing credential"

    assert await service.list_versions(component.id, only_available=True) == []
    assert len(await service.list_versions(component.id)) == 1


async def test_mark_available_clears_the_reason(session) -> None:
    service = ComponentService(session)
    component = await service.register_component(ComponentType.PARSER, pypdf.KEY, "PyPDF")
    version = await service.register_version(component_id=component.id, version="1")
    await service.mark_unavailable(version.id, "missing credential")

    updated = await service.mark_available(version.id)

    assert updated.is_available is True
    assert updated.unavailable_reason is None
