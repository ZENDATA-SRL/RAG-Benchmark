from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.components.models import Component, ComponentVersion
from src.components.service import ComponentService
from src.core.get_or_create import get_or_create_reporting
from src.core.hashing import combined_config_hash, config_hash, hash_json
from src.infrastructure.database.enums import RetrievalStrategy
from src.pipelines import naming
from src.pipelines.constants import SUPPORTED_RETRIEVAL_STRATEGIES
from src.pipelines.exceptions import (
    ChunkingConfigurationNotFoundError,
    ProfileNotFoundError,
    UnsupportedChunkerScopeError,
    UnsupportedRetrievalFeatureError,
)
from src.pipelines.models import (
    ChunkingConfiguration,
    ChunkingProfile,
    EmbeddingProfile,
    ParsingProfile,
    RetrievalProfile,
    VectorStoreProfile,
)
from src.pipelines.repository import ChunkingConfigurationRepository, ProfileRepository

SUPPORTED_CHUNKER_SCOPE = "document"


class ProfileService:
    """Creation of pipeline profiles, deduplicated by `config_hash`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.components = ComponentService(session)

    async def get_or_create_parsing_profile(
        self,
        *,
        component_version_id: uuid.UUID,
        params: dict[str, Any] | None = None,
    ) -> tuple[ParsingProfile, bool]:
        """Return the parsing profile for a (component version, params) pair.

        Returns:
            The profile and whether this call created it.

        Raises:
            InvalidComponentParamsError: If the parameters violate the version's schema.
            ComponentVersionNotFoundError: If the component version does not exist.
        """
        await self.components.validate_params(component_version_id, params or {})
        component, _schema = await self._component(component_version_id)
        return await self._get_or_create(
            ParsingProfile,
            component_version_id=component_version_id,
            name=naming.parsing_profile_name(component),
            columns={"params": params or {}},
        )

    async def get_or_create_chunking_profile(
        self,
        *,
        component_version_id: uuid.UUID,
        strategy: str,
        chunk_size: int | None = None,
        overlap: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[ChunkingProfile, bool]:
        """Return the chunking profile for a chunker configuration.

        `chunk_size` and `overlap` are folded into the parameters that are validated, since
        they are promoted columns of the same contract the schema describes: validating only
        `params` would let an out-of-range chunk size through to the worker.

        Returns:
            The profile and whether this call created it.

        Raises:
            UnsupportedChunkerScopeError: If the component version declares a scope other
                than `document`.
            ProfileNotFoundError: If the component version does not exist.
            InvalidComponentParamsError: If the parameters violate the version's schema.
        """
        await self._assert_document_scope(component_version_id)
        effective = _effective_chunker_params(
            params, chunk_size=chunk_size, overlap=overlap
        )
        await self.components.validate_params(component_version_id, effective)
        component, schema = await self._component(component_version_id)
        return await self._get_or_create(
            ChunkingProfile,
            component_version_id=component_version_id,
            name=naming.chunking_profile_name(
                component,
                chunk_size=naming.schema_value(effective, schema, "chunk_size"),
                overlap=naming.schema_value(effective, schema, "overlap"),
            ),
            columns={
                "strategy": strategy,
                "chunk_size": chunk_size,
                "overlap": overlap,
                "params": params or {},
            },
        )

    async def get_or_create_embedding_profile(
        self,
        *,
        component_version_id: uuid.UUID,
        modality: str = "text",
        dimensions: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[EmbeddingProfile, bool]:
        """Return the embedding profile for an embedder configuration.

        Returns:
            The profile and whether this call created it.

        Raises:
            InvalidComponentParamsError: If the parameters violate the version's schema.
            ComponentVersionNotFoundError: If the component version does not exist.
        """
        await self.components.validate_params(component_version_id, params or {})
        component, schema = await self._component(component_version_id)
        return await self._get_or_create(
            EmbeddingProfile,
            component_version_id=component_version_id,
            name=naming.embedding_profile_name(
                component,
                model=naming.schema_value(params or {}, schema, "model_name"),
                dimensions=dimensions,
            ),
            columns={
                "modality": modality,
                "dimensions": dimensions,
                "params": params or {},
            },
        )

    async def get_or_create_vector_store_profile(
        self,
        *,
        component_version_id: uuid.UUID,
        index_params: dict[str, Any] | None = None,
    ) -> tuple[VectorStoreProfile, bool]:
        """Return the vector store profile for an index configuration.

        Returns:
            The profile and whether this call created it.

        Raises:
            InvalidComponentParamsError: If the parameters violate the version's schema.
            ComponentVersionNotFoundError: If the component version does not exist.
        """
        await self.components.validate_params(component_version_id, index_params or {})
        component, schema = await self._component(component_version_id)
        return await self._get_or_create(
            VectorStoreProfile,
            component_version_id=component_version_id,
            name=naming.vector_store_profile_name(
                component,
                space=naming.schema_value(index_params or {}, schema, "space"),
            ),
            columns={"index_params": index_params or {}},
        )

    async def get_parsing_profile(self, profile_id: uuid.UUID) -> ParsingProfile:
        """Return a parsing profile by id.

        Raises:
            ProfileNotFoundError: If it does not exist.
        """
        profile = await ProfileRepository(self.session, ParsingProfile).get_by_id(
            profile_id
        )
        if profile is None:
            raise ProfileNotFoundError("parsing", profile_id)
        return profile

    async def get_chunking_profile(self, profile_id: uuid.UUID) -> ChunkingProfile:
        """Return a chunking profile by id.

        Raises:
            ProfileNotFoundError: If it does not exist.
        """
        profile = await ProfileRepository(self.session, ChunkingProfile).get_by_id(
            profile_id
        )
        if profile is None:
            raise ProfileNotFoundError("chunking", profile_id)
        return profile

    async def get_embedding_profile(self, profile_id: uuid.UUID) -> EmbeddingProfile:
        """Return an embedding profile by id.

        Raises:
            ProfileNotFoundError: If it does not exist.
        """
        profile = await ProfileRepository(self.session, EmbeddingProfile).get_by_id(
            profile_id
        )
        if profile is None:
            raise ProfileNotFoundError("embedding", profile_id)
        return profile

    async def get_vector_store_profile(
        self, profile_id: uuid.UUID
    ) -> VectorStoreProfile:
        """Return a vector store profile by id.

        Raises:
            ProfileNotFoundError: If it does not exist.
        """
        profile = await ProfileRepository(self.session, VectorStoreProfile).get_by_id(
            profile_id
        )
        if profile is None:
            raise ProfileNotFoundError("vector store", profile_id)
        return profile

    async def list_parsing_profiles(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[ParsingProfile], int]:
        """One page of parsing profiles and the size of the whole set."""
        repository = ProfileRepository(self.session, ParsingProfile)
        return await repository.list(
            limit=limit, offset=offset
        ), await repository.count()

    async def list_chunking_profiles(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[ChunkingProfile], int]:
        """One page of chunking profiles and the size of the whole set."""
        repository = ProfileRepository(self.session, ChunkingProfile)
        return await repository.list(
            limit=limit, offset=offset
        ), await repository.count()

    async def list_embedding_profiles(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[EmbeddingProfile], int]:
        """One page of embedding profiles and the size of the whole set."""
        repository = ProfileRepository(self.session, EmbeddingProfile)
        return await repository.list(
            limit=limit, offset=offset
        ), await repository.count()

    async def list_vector_store_profiles(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[VectorStoreProfile], int]:
        """One page of vector store profiles and the size of the whole set."""
        repository = ProfileRepository(self.session, VectorStoreProfile)
        return await repository.list(
            limit=limit, offset=offset
        ), await repository.count()

    async def get_or_create_retrieval_profile(
        self,
        *,
        top_k: int,
        strategy: RetrievalStrategy = RetrievalStrategy.DENSE,
        score_threshold: float | None = None,
    ) -> tuple[RetrievalProfile, bool]:
        """Return the retrieval profile for a retrieval configuration.

        Unlike the other profiles this one has no component version of its own, so the
        hash covers its columns directly.

        Args:
            top_k: Number of results returned.
            strategy: Only `dense` is executable today.
            score_threshold: Hits scoring below it are dropped.

        Returns:
            The profile and whether this call created it.

        Raises:
            UnsupportedRetrievalFeatureError: If the strategy is not executable yet.
        """
        strategy = RetrievalStrategy(strategy)
        if strategy not in SUPPORTED_RETRIEVAL_STRATEGIES:
            raise UnsupportedRetrievalFeatureError("strategy", strategy.value)
        columns: dict[str, Any] = {
            "top_k": top_k,
            "strategy": strategy,
            "score_threshold": score_threshold,
        }
        digest = hash_json({**columns, "strategy": strategy.value})
        repository = ProfileRepository(self.session, RetrievalProfile)

        base = naming.retrieval_profile_name(
            strategy.value, top_k=top_k, score_threshold=score_threshold
        )

        async def create() -> RetrievalProfile:
            name = naming.disambiguated(
                base, digest, taken=await repository.name_taken(base)
            )
            profile = repository.add(
                RetrievalProfile(name=name, config_hash=digest, **columns)
            )
            await self.session.flush()
            return profile

        return await get_or_create_reporting(
            self.session,
            lookup=lambda: repository.get_by_config_hash(digest),
            create=create,
        )

    async def get_retrieval_profile(self, profile_id: uuid.UUID) -> RetrievalProfile:
        """Return a retrieval profile by id.

        Raises:
            ProfileNotFoundError: If it does not exist.
        """
        profile = await ProfileRepository(self.session, RetrievalProfile).get_by_id(
            profile_id
        )
        if profile is None:
            raise ProfileNotFoundError("retrieval", profile_id)
        return profile

    async def list_retrieval_profiles(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[RetrievalProfile], int]:
        """One page of retrieval profiles and the size of the whole set."""
        repository = ProfileRepository(self.session, RetrievalProfile)
        return await repository.list(
            limit=limit, offset=offset
        ), await repository.count()

    async def _get_or_create(
        self,
        model: type[Any],
        *,
        component_version_id: uuid.UUID,
        name: str,
        columns: dict[str, Any],
    ) -> tuple[Any, bool]:
        """Shared get-or-create for the profile tables.

        The hash covers the component version and **every** behavioural column, including
        the ones promoted out of `params` such as strategy, chunk size, overlap and
        modality. `name` is derived from the behaviour and only written on creation; it
        gains a short hash suffix when another profile already reads the same, for instance
        two embedders differing only in a parameter the name does not show.
        """
        digest = config_hash(component_version_id, columns)
        repository = ProfileRepository(self.session, model)

        async def create() -> Any:
            profile = repository.add(
                model(
                    name=naming.disambiguated(
                        name, digest, taken=await repository.name_taken(name)
                    ),
                    component_version_id=component_version_id,
                    config_hash=digest,
                    **columns,
                )
            )
            await self.session.flush()
            return profile

        return await get_or_create_reporting(
            self.session,
            lookup=lambda: repository.get_by_config_hash(digest),
            create=create,
        )

    async def _component(self, component_version_id: uuid.UUID) -> tuple[str, dict]:
        """The label of a component version (`pypdf@1`) and its parameter schema."""
        version = await self.session.get(ComponentVersion, component_version_id)
        if version is None:
            raise ProfileNotFoundError("component version", component_version_id)
        component = await self.session.get(Component, version.component_id)
        return naming.component_label(component.key, version.version), (
            version.params_schema or {}
        )

    async def _assert_document_scope(self, component_version_id: uuid.UUID) -> None:
        """Reject chunkers whose declared scope is not `document`."""
        version = await self.session.get(ComponentVersion, component_version_id)
        if version is None:
            raise ProfileNotFoundError(
                "chunker component version", component_version_id
            )
        scope = version.capabilities.get("scope", SUPPORTED_CHUNKER_SCOPE)
        if scope != SUPPORTED_CHUNKER_SCOPE:
            raise UnsupportedChunkerScopeError(scope)


def _effective_chunker_params(
    params: dict[str, Any] | None, *, chunk_size: int | None, overlap: int | None
) -> dict[str, Any]:
    """Fold the promoted columns back into the params a chunker schema describes.

    Mirrors what the worker does when it loads a profile, so validation at the API boundary
    sees exactly the parameters the chunker will receive.
    """
    effective = dict(params or {})
    if chunk_size is not None:
        effective.setdefault("chunk_size", chunk_size)
    if overlap is not None:
        effective.setdefault("overlap", overlap)
    return effective


@dataclasses.dataclass(frozen=True)
class ExpandedConfiguration:
    """A configuration together with the two profiles it is made of.

    Returned as one object because the UI shows "pypdf + recursive512" as a label: resolving
    it client-side would cost three calls to render one row.
    """

    configuration: ChunkingConfiguration
    parsing_profile: ParsingProfile
    chunking_profile: ChunkingProfile


@dataclasses.dataclass(frozen=True)
class ComposedConfiguration:
    """The result of composing a configuration from two profiles given by value."""

    expanded: ExpandedConfiguration
    parsing_profile_created: bool
    chunking_profile_created: bool
    configuration_created: bool


class ChunkingConfigurationService:
    """The (parsing, chunking) pair that chunk-level gold is anchored to."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.configurations = ChunkingConfigurationRepository(session)
        self.parsing_profiles = ProfileRepository(session, ParsingProfile)
        self.chunking_profiles = ProfileRepository(session, ChunkingProfile)

    async def get_or_create(
        self,
        *,
        parsing_profile_id: uuid.UUID,
        chunking_profile_id: uuid.UUID,
    ) -> tuple[ChunkingConfiguration, bool]:
        """Return the configuration for a profile pair, creating it once.

        Args:
            parsing_profile_id: Parsing profile of the pair.
            chunking_profile_id: Chunking profile of the pair.

        Returns:
            The configuration for the pair and whether this call created it.

        Raises:
            ProfileNotFoundError: If either profile does not exist.
        """
        parsing = await self.parsing_profiles.get_by_id(parsing_profile_id)
        if parsing is None:
            raise ProfileNotFoundError("parsing", parsing_profile_id)
        chunking = await self.chunking_profiles.get_by_id(chunking_profile_id)
        if chunking is None:
            raise ProfileNotFoundError("chunking", chunking_profile_id)

        digest = combined_config_hash(parsing.config_hash, chunking.config_hash)
        label = naming.chunking_configuration_name(parsing.name, chunking.name)

        async def create() -> ChunkingConfiguration:
            configuration = self.configurations.add(
                ChunkingConfiguration(
                    name=naming.disambiguated(
                        label,
                        digest,
                        taken=await self.configurations.name_taken(label),
                    ),
                    parsing_profile_id=parsing_profile_id,
                    chunking_profile_id=chunking_profile_id,
                    config_hash=digest,
                )
            )
            await self.session.flush()
            return configuration

        return await get_or_create_reporting(
            self.session,
            lookup=lambda: self.configurations.get_by_config_hash(digest),
            create=create,
        )

    async def get(self, configuration_id: uuid.UUID) -> ChunkingConfiguration:
        """Return a configuration by id.

        Raises:
            ChunkingConfigurationNotFoundError: If it does not exist.
        """
        configuration = await self.configurations.get_by_id(configuration_id)
        if configuration is None:
            raise ChunkingConfigurationNotFoundError(configuration_id)
        return configuration

    async def expand(
        self, configuration: ChunkingConfiguration
    ) -> ExpandedConfiguration:
        """Resolve the two profiles of a configuration.

        Raises:
            ProfileNotFoundError: If either profile is missing, which the `RESTRICT` foreign
                keys make impossible in practice.
        """
        parsing = await self.parsing_profiles.get_by_id(
            configuration.parsing_profile_id
        )
        if parsing is None:
            raise ProfileNotFoundError("parsing", configuration.parsing_profile_id)
        chunking = await self.chunking_profiles.get_by_id(
            configuration.chunking_profile_id
        )
        if chunking is None:
            raise ProfileNotFoundError("chunking", configuration.chunking_profile_id)
        return ExpandedConfiguration(
            configuration=configuration,
            parsing_profile=parsing,
            chunking_profile=chunking,
        )

    async def list_expanded(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[ExpandedConfiguration], int]:
        """One page of configurations with their profiles resolved, and the total."""
        configurations = await self.configurations.list(limit=limit, offset=offset)
        expanded = [
            await self.expand(configuration) for configuration in configurations
        ]
        return expanded, await self.configurations.count()

    async def compose(
        self,
        *,
        parsing_component_version_id: uuid.UUID,
        parsing_params: dict[str, Any] | None = None,
        chunking_component_version_id: uuid.UUID,
        chunking_strategy: str,
        chunk_size: int | None = None,
        overlap: int | None = None,
        chunking_params: dict[str, Any] | None = None,
    ) -> ComposedConfiguration:
        """Create both profiles and their configuration in one act.

        The shortcut behind a single UI form: three get-or-creates in one transaction, so a
        half-composed configuration cannot be left behind if the second profile is rejected.
        The granular endpoints remain, since anything that reuses an existing profile should
        reference it by id rather than restate it by value.

        Returns:
            The expanded configuration and which of the three rows this call created.
        """
        profiles = ProfileService(self.session)
        parsing, parsing_created = await profiles.get_or_create_parsing_profile(
            component_version_id=parsing_component_version_id,
            params=parsing_params,
        )
        chunking, chunking_created = await profiles.get_or_create_chunking_profile(
            component_version_id=chunking_component_version_id,
            strategy=chunking_strategy,
            chunk_size=chunk_size,
            overlap=overlap,
            params=chunking_params,
        )
        configuration, configuration_created = await self.get_or_create(
            parsing_profile_id=parsing.id,
            chunking_profile_id=chunking.id,
        )
        return ComposedConfiguration(
            expanded=ExpandedConfiguration(
                configuration=configuration,
                parsing_profile=parsing,
                chunking_profile=chunking,
            ),
            parsing_profile_created=parsing_created,
            chunking_profile_created=chunking_created,
            configuration_created=configuration_created,
        )
