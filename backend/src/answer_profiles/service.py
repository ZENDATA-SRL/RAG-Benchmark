from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.answer_profiles.exceptions import (
    AnswerProfileNotFoundError,
    AnswerSystemNotAvailableError,
    InvalidParentProfileError,
    NotAnAnswerSystemError,
)
from src.answer_profiles.models import AnswerProfile
from src.answer_profiles.repository import AnswerProfileRepository
from src.components.exceptions import ComponentVersionNotFoundError
from src.components.models import Component, ComponentVersion
from src.components.service import ComponentService
from src.core.get_or_create import get_or_create_reporting
from src.core.hashing import config_hash
from src.infrastructure.database.enums import ComponentType
from src.pipelines import naming


class AnswerProfileService:
    """Creation of answer profiles, deduplicated by `config_hash`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.profiles = AnswerProfileRepository(session)
        self.components = ComponentService(session)

    async def get_or_create(
        self,
        *,
        component_version_id: uuid.UUID,
        params: dict[str, Any],
        parent_profile_id: uuid.UUID | None = None,
    ) -> tuple[AnswerProfile, bool]:
        """Return the profile for an answer system and its parameters, creating it if absent.

        The schema's defaults are written into the parameters before hashing, so leaving a
        parameter out and giving its default value are the same profile. The name is
        derived from the system, the provider, the model and the temperature, with a short
        hash suffix when two profiles differ only in something else, such as the prompt.
        The parent is recorded only when the profile is created.

        Returns:
            The profile and whether this call created it.

        Raises:
            ComponentVersionNotFoundError: If the component version does not exist.
            NotAnAnswerSystemError: If the component is not an answer system.
            AnswerSystemNotAvailableError: If the version is marked unavailable.
            InvalidComponentParamsError: If the parameters violate the version's schema.
            AnswerProfileNotFoundError: If the parent profile does not exist.
            InvalidParentProfileError: If the parent is on another component version.
        """
        version, component = await self._answer_system(component_version_id)
        schema = version.params_schema or {}
        effective = _with_defaults(params, schema)
        await self.components.validate_params(component_version_id, effective)
        if parent_profile_id is not None:
            parent = await self.get(parent_profile_id)
            if parent.component_version_id != component_version_id:
                raise InvalidParentProfileError(parent_profile_id)

        digest = config_hash(component_version_id, effective)
        name = naming.answer_profile_name(
            naming.component_label(component.key, version.version),
            provider=effective.get("provider"),
            model=effective.get("model"),
            temperature=effective.get("temperature"),
        )

        async def create() -> AnswerProfile:
            profile = self.profiles.add(
                AnswerProfile(
                    name=naming.disambiguated(
                        name, digest, taken=await self.profiles.name_taken(name)
                    ),
                    component_version_id=component_version_id,
                    params=effective,
                    config_hash=digest,
                    parent_profile_id=parent_profile_id,
                )
            )
            await self.session.flush()
            return profile

        return await get_or_create_reporting(
            self.session,
            lookup=lambda: self.profiles.get_by_config_hash(digest),
            create=create,
        )

    async def get(self, profile_id: uuid.UUID) -> AnswerProfile:
        """Return an answer profile.

        Raises:
            AnswerProfileNotFoundError: If it does not exist.
        """
        profile = await self.profiles.get_by_id(profile_id)
        if profile is None:
            raise AnswerProfileNotFoundError(profile_id)
        return profile

    async def changed_params(
        self, profile: AnswerProfile
    ) -> list[tuple[str, Any, Any]]:
        """The parameters that differ from the parent's, as (key, parent, value).

        Empty when the profile has no parent or the parent was removed.
        """
        if profile.parent_profile_id is None:
            return []
        parent = await self.profiles.get_by_id(profile.parent_profile_id)
        if parent is None:
            return []
        return [
            (key, parent.params.get(key), profile.params.get(key))
            for key in sorted(set(parent.params) | set(profile.params))
            if parent.params.get(key) != profile.params.get(key)
        ]

    async def list(
        self,
        *,
        component_version_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[AnswerProfile], int]:
        """One page of answer profiles, by name, and the total."""
        return await self.profiles.list(
            component_version_id=component_version_id, limit=limit, offset=offset
        )

    async def runnable_system(
        self, profile: AnswerProfile
    ) -> tuple[ComponentVersion, Component]:
        """The version and component a profile runs, if they can be run now.

        Raises:
            AnswerSystemNotAvailableError: If the version is marked unavailable.
        """
        return await self._answer_system(profile.component_version_id)

    async def component_of(
        self, profile: AnswerProfile
    ) -> tuple[ComponentVersion, Component]:
        """The version and component a profile runs, available or not."""
        version = await self.session.get(ComponentVersion, profile.component_version_id)
        return version, await self.session.get(Component, version.component_id)

    async def _answer_system(
        self, component_version_id: uuid.UUID
    ) -> tuple[ComponentVersion, Component]:
        version = await self.session.get(ComponentVersion, component_version_id)
        if version is None:
            raise ComponentVersionNotFoundError(component_version_id)
        component = await self.session.get(Component, version.component_id)
        if component.type != ComponentType.ANSWER_SYSTEM:
            raise NotAnAnswerSystemError(component_version_id, component.type.value)
        if not version.is_available:
            raise AnswerSystemNotAvailableError(
                component_version_id, version.unavailable_reason
            )
        return version, component


def _with_defaults(params: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """The parameters with the schema's top-level defaults filled in."""
    effective = dict(params)
    for key, spec in (schema.get("properties") or {}).items():
        if key not in effective and "default" in spec:
            effective[key] = spec["default"]
    return effective
