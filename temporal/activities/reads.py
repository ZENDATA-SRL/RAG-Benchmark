from __future__ import annotations

import dataclasses
import uuid

from src.components.models import ComponentVersion
from src.pipelines.exceptions import ProfileNotFoundError
from src.pipelines.models import ChunkingConfiguration, ChunkingProfile, ParsingProfile
from temporalio import activity

from temporal.config import activity_session


@dataclasses.dataclass
class ConfigurationResolved:
    """The identifiers a workflow needs to drive parse then chunk of one document.

    Workflows never touch the database, so this is read once via an activity and threaded
    through the child workflow instead.
    """

    parsing_profile_id: str
    chunking_profile_id: str


@activity.defn
async def resolve_configuration(chunking_configuration_id: str) -> ConfigurationResolved:
    """Read the parsing and chunking profiles a chunking configuration points at.

    Raises:
        ProfileNotFoundError: If the configuration does not exist.
    """
    async with activity_session() as session:
        configuration = await session.get(
            ChunkingConfiguration, uuid.UUID(chunking_configuration_id)
        )
        if configuration is None:
            raise ProfileNotFoundError("chunking configuration", chunking_configuration_id)
        return ConfigurationResolved(
            parsing_profile_id=str(configuration.parsing_profile_id),
            chunking_profile_id=str(configuration.chunking_profile_id),
        )


async def load_parsing_component(
    session, parsing_profile_id: uuid.UUID
) -> tuple[str, dict]:
    """Return the parser key and params of a parsing profile.

    Raises:
        ProfileNotFoundError: If the profile or its component version is missing.
    """
    profile = await session.get(ParsingProfile, parsing_profile_id)
    if profile is None:
        raise ProfileNotFoundError("parsing", parsing_profile_id)
    key = await _component_key(session, profile.component_version_id, "parsing")
    return key, dict(profile.params)


async def load_chunking_component(
    session, chunking_profile_id: uuid.UUID
) -> tuple[str, dict]:
    """Return the chunker key and effective params of a chunking profile.

    The promoted columns `chunk_size` and `overlap` are folded back into the params the
    chunker reads, so the profile stays the single source of truth for both.

    Raises:
        ProfileNotFoundError: If the profile or its component version is missing.
    """
    profile = await session.get(ChunkingProfile, chunking_profile_id)
    if profile is None:
        raise ProfileNotFoundError("chunking", chunking_profile_id)
    key = await _component_key(session, profile.component_version_id, "chunking")
    params = dict(profile.params)
    if profile.chunk_size is not None:
        params.setdefault("chunk_size", profile.chunk_size)
    if profile.overlap is not None:
        params.setdefault("overlap", profile.overlap)
    return key, params


async def _component_key(session, component_version_id: uuid.UUID, kind: str) -> str:
    version = await session.get(ComponentVersion, component_version_id)
    if version is None:
        raise ProfileNotFoundError(f"{kind} component version", component_version_id)
    await session.refresh(version, ["component"])
    return version.component.key
