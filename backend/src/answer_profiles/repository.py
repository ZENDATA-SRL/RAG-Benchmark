from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.answer_profiles.models import AnswerProfile


class AnswerProfileRepository:
    """Data access for `answer_profiles`, keyed by `config_hash`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, profile: AnswerProfile) -> AnswerProfile:
        self.session.add(profile)
        return profile

    async def get_by_id(self, profile_id: uuid.UUID) -> AnswerProfile | None:
        return await self.session.get(AnswerProfile, profile_id)

    async def get_by_config_hash(self, config_hash: str) -> AnswerProfile | None:
        stmt = select(AnswerProfile).where(AnswerProfile.config_hash == config_hash)
        return await self.session.scalar(stmt)

    async def name_taken(self, name: str) -> bool:
        stmt = select(AnswerProfile.id).where(AnswerProfile.name == name).limit(1)
        return await self.session.scalar(stmt) is not None

    async def list(
        self,
        *,
        component_version_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[AnswerProfile], int]:
        """One page of profiles by name, optionally of one component version, and the total."""
        stmt = select(AnswerProfile)
        if component_version_id is not None:
            stmt = stmt.where(
                AnswerProfile.component_version_id == component_version_id
            )
        total = await self.session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        rows = await self.session.scalars(
            stmt.order_by(AnswerProfile.name).limit(limit).offset(offset)
        )
        return rows.all(), total or 0
