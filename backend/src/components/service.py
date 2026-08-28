from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

import jsonschema.validators
from jsonschema.exceptions import SchemaError
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.builtin import BUILTIN_KEYS
from src.components.exceptions import (
    ComponentNotFoundError,
    ComponentVersionNotFoundError,
    InvalidComponentParamsError,
    InvalidParamsSchemaError,
    UnknownBuiltinError,
    UnsupportedRuntimeError,
)
from src.components.models import Component, ComponentVersion
from src.components.repository import ComponentRepository, ComponentVersionRepository
from src.core.get_or_create import get_or_create
from src.infrastructure.database.enums import ComponentType, RuntimeType

# Only in-process components exist in the MVP; `http` is modelled but has no client
SUPPORTED_RUNTIMES = (RuntimeType.BUILTIN,)


class ComponentService:
    """Registration and validation of pluggable components."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.components = ComponentRepository(session)
        self.versions = ComponentVersionRepository(session)

    async def register_component(
        self, component_type: ComponentType, key: str, display_name: str
    ) -> Component:
        """Return the component for `(type, key)`, creating it if absent.

        Get-or-create rather than insert so the startup seed is idempotent and adding a
        component needs no migration: the pair `(type, key)` is the identity, and
        `display_name` is a label that is not part of it.

        Args:
            component_type: Role the component plays in a pipeline.
            key: Stable identifier within the type, e.g. `pypdf`.
            display_name: Human-readable label shown in the UI.

        Returns:
            The pre-existing component or the newly created one.
        """

        async def create() -> Component:
            component = self.components.add(
                Component(type=component_type, key=key, display_name=display_name)
            )
            await self.session.flush()
            return component

        return await get_or_create(
            self.session,
            lookup=lambda: self.components.get_by_type_and_key(component_type, key),
            create=create,
        )

    async def register_version(
        self,
        *,
        component_id: uuid.UUID,
        version: str,
        runtime: RuntimeType = RuntimeType.BUILTIN,
        endpoint: str | None = None,
        params_schema: dict[str, Any] | None = None,
        capabilities: dict[str, Any] | None = None,
    ) -> ComponentVersion:
        """Return the version for `(component_id, version)`, creating it if absent.

        Validates before writing: the `params_schema` must be a syntactically valid JSON
        Schema, because it is what the UI renders a form from (RT-U01), and the runtime must
        be one this build can actually execute.

        Args:
            component_id: Component the version belongs to.
            version: Version label, unique within the component.
            runtime: Execution model; only `builtin` is accepted in the MVP.
            endpoint: Base URL for an `http` runtime; unused while only `builtin` exists.
            params_schema: JSON Schema of the accepted parameters.
            capabilities: Declared capabilities, e.g. `formats`, `modalities`, `scope`.

        Returns:
            The pre-existing version or the newly created one.

        Raises:
            ComponentNotFoundError: If the component does not exist.
            UnsupportedRuntimeError: If the runtime is not executable in this version.
            UnknownBuiltinError: If the component key was never declared as a builtin.            InvalidParamsSchemaError: If `params_schema` is not a valid JSON Schema.
        """
        component = await self.components.get_by_id(component_id)
        if component is None:
            raise ComponentNotFoundError(component_id)

        if runtime not in SUPPORTED_RUNTIMES:
            raise UnsupportedRuntimeError(runtime)

        registry = BUILTIN_KEYS.get(component.type)
        if registry is not None and component.key not in registry:
            raise UnknownBuiltinError(component.type, component.key)

        schema = params_schema if params_schema is not None else {}
        _assert_valid_schema(schema)

        async def create() -> ComponentVersion:
            created = self.versions.add(
                ComponentVersion(
                    component_id=component_id,
                    version=version,
                    runtime=runtime,
                    endpoint=endpoint,
                    params_schema=schema,
                    capabilities=capabilities or {},
                )
            )
            await self.session.flush()
            return created

        return await get_or_create(
            self.session,
            lookup=lambda: self.versions.get_version_by_component_and_version(
                component_id, version
            ),
            create=create,
        )

    async def validate_params(
        self, component_version_id: uuid.UUID, params: dict[str, Any]
    ) -> None:
        """Check a profile's parameters against the version's declared schema.

        Called before a profile is created, so an invalid configuration is rejected at the
        API boundary instead of failing inside a workflow activity hours later.

        Args:
            component_version_id: Version whose `params_schema` is the contract.
            params: Parameters to validate.

        Raises:
            ComponentVersionNotFoundError: If the version does not exist.
            InvalidComponentParamsError: If the parameters violate the schema; the field
                path of the first offending value is reported.
        """
        component_version = await self.versions.get_version(component_version_id)
        if component_version is None:
            raise ComponentVersionNotFoundError(component_version_id)

        schema = component_version.params_schema or {}
        if not schema:
            return

        try:
            jsonschema.validate(instance=params, schema=schema)
        except JsonSchemaValidationError as error:
            raise InvalidComponentParamsError(
                field_path=_field_path(error), reason=error.message
            ) from error

    async def mark_unavailable(self, version_id: uuid.UUID, reason: str) -> ComponentVersion:
        """Flag a version as not executable, keeping the row and the reason.

        Excluding a component from the choices is a state change and not a deletion: the
        profiles and artefacts that already reference it must stay readable, and the UI has
        to be able to explain *why* the option disappeared.

        Args:
            version_id: Version to exclude.
            reason: Why it cannot be executed, e.g. a missing credential.

        Returns:
            The updated version.

        Raises:
            ComponentVersionNotFoundError: If the version does not exist.
        """
        component_version = await self.versions.get_version(version_id)
        if component_version is None:
            raise ComponentVersionNotFoundError(version_id)

        component_version.is_available = False
        component_version.unavailable_reason = reason
        await self.session.flush()
        return component_version

    async def mark_available(self, version_id: uuid.UUID) -> ComponentVersion:
        """Clear the unavailability of a version, dropping the stored reason."""
        component_version = await self.versions.get_version(version_id)
        if component_version is None:
            raise ComponentVersionNotFoundError(version_id)

        component_version.is_available = True
        component_version.unavailable_reason = None
        await self.session.flush()
        return component_version

    async def list_components(
        self, component_type: ComponentType | None = None
    ) -> Sequence[Component]:
        """List the registered components, optionally filtered by type."""
        return await self.components.list_by_type(component_type)

    async def list_versions(
        self, component_id: uuid.UUID, *, only_available: bool = False
    ) -> Sequence[ComponentVersion]:
        """List the versions of a component.

        Raises:
            ComponentNotFoundError: If the component does not exist, so the caller gets a
                404 instead of an empty list that looks like a component with no versions.
        """
        if await self.components.get_by_id(component_id) is None:
            raise ComponentNotFoundError(component_id)
        return await self.versions.list_versions(component_id, only_available=only_available)

    async def get_component(self, component_id: uuid.UUID) -> Component:
        """Return a component by id.

        Raises:
            ComponentNotFoundError: If it does not exist.
        """
        component = await self.components.get_by_id(component_id)
        if component is None:
            raise ComponentNotFoundError(component_id)
        return component


def _assert_valid_schema(schema: dict[str, Any]) -> None:
    """Reject a `params_schema` that no validator could ever apply."""
    try:
        validator = jsonschema.validators.validator_for(schema)
        validator.check_schema(schema)
    except SchemaError as error:
        raise InvalidParamsSchemaError(error.message) from error


def _field_path(error: JsonSchemaValidationError) -> str:
    """Render the location of a validation error as a dotted path.

    Turns the deque of keys and indexes jsonschema reports into something a form can point
    at, e.g. `separators.0`.
    """
    return ".".join(str(part) for part in error.absolute_path)
