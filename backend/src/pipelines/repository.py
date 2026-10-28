from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.pipelines.models import (
    ChunkingConfiguration,
    ChunkingProfile,
    EmbeddingProfile,
    ParsingProfile,
    RetrievalProfile,
    VectorStoreProfile,
)

# The five profiles share the same `config_hash` dedup key, so their data access is one
# generic class parametrised by model rather than five near-identical copies.
ProfileT = TypeVar(
    "ProfileT",
    ParsingProfile,
    ChunkingProfile,
    EmbeddingProfile,
    VectorStoreProfile,
    RetrievalProfile,
)


class ProfileRepository(Generic[ProfileT]):
    """Data access for a pipeline profile table, keyed by `config_hash`."""

    def __init__(self, session: AsyncSession, model: type[ProfileT]) -> None:
        self.session = session
        self.model = model

    def add(self, profile: ProfileT) -> ProfileT:
        self.session.add(profile)
        return profile

    async def get_by_id(self, profile_id: uuid.UUID) -> ProfileT | None:
        return await self.session.get(self.model, profile_id)

    async def get_by_config_hash(self, config_hash: str) -> ProfileT | None:
        """Look up a profile by its content-addressed dedup key."""
        stmt = select(self.model).where(self.model.config_hash == config_hash)
        return await self.session.scalar(stmt)

    async def name_taken(self, name: str) -> bool:
        stmt = select(self.model.id).where(self.model.name == name).limit(1)
        return await self.session.scalar(stmt) is not None

    async def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[ProfileT]:
        stmt = select(self.model).order_by(self.model.name).limit(limit).offset(offset)
        result = await self.session.scalars(stmt)
        return result.all()

    async def count(self) -> int:
        return (
            await self.session.scalar(select(func.count()).select_from(self.model)) or 0
        )


class ChunkingConfigurationRepository:
    """Data access for `chunking_configurations`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, configuration: ChunkingConfiguration) -> ChunkingConfiguration:
        self.session.add(configuration)
        return configuration

    async def get_by_id(
        self, configuration_id: uuid.UUID
    ) -> ChunkingConfiguration | None:
        return await self.session.get(ChunkingConfiguration, configuration_id)

    async def get_by_config_hash(
        self, config_hash: str
    ) -> ChunkingConfiguration | None:
        stmt = select(ChunkingConfiguration).where(
            ChunkingConfiguration.config_hash == config_hash
        )
        return await self.session.scalar(stmt)

    async def name_taken(self, name: str) -> bool:
        stmt = (
            select(ChunkingConfiguration.id)
            .where(ChunkingConfiguration.name == name)
            .limit(1)
        )
        return await self.session.scalar(stmt) is not None

    async def get_by_profiles(
        self, parsing_profile_id: uuid.UUID, chunking_profile_id: uuid.UUID
    ) -> ChunkingConfiguration | None:
        """Look up the configuration for a (parsing, chunking) profile pair."""
        stmt = select(ChunkingConfiguration).where(
            ChunkingConfiguration.parsing_profile_id == parsing_profile_id,
            ChunkingConfiguration.chunking_profile_id == chunking_profile_id,
        )
        return await self.session.scalar(stmt)

    async def list(
        self, *, limit: int = 50, offset: int = 0
    ) -> Sequence[ChunkingConfiguration]:
        stmt = (
            select(ChunkingConfiguration)
            .order_by(ChunkingConfiguration.name)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.scalars(stmt)
        return result.all()

    async def count(self) -> int:
        return (
            await self.session.scalar(
                select(func.count()).select_from(ChunkingConfiguration)
            )
            or 0
        )
