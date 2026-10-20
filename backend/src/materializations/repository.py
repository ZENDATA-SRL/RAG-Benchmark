from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.materializations.models import MaterializationRun


class MaterializationRunRepository:
    """Data access for `materialization_runs`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, run: MaterializationRun) -> MaterializationRun:
        self.session.add(run)
        return run

    async def get_by_id(self, run_id: uuid.UUID) -> MaterializationRun | None:
        return await self.session.get(MaterializationRun, run_id)

    async def get_by_workflow_id(self, workflow_id: str) -> MaterializationRun | None:
        """Resolve a run by its deterministic Temporal workflow id (RT-O01)."""
        stmt = select(MaterializationRun).where(
            MaterializationRun.workflow_id == workflow_id
        )
        return await self.session.scalar(stmt)

    async def list(
        self,
        *,
        corpus_id: uuid.UUID | None = None,
        chunking_configuration_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[MaterializationRun]:
        """Run history, newest first, optionally narrowed to a corpus or configuration.

        `id` breaks ties because `created_at` comes from `now()`, which is identical for rows
        written by the same transaction: without it a page boundary could drop or repeat a run.
        """
        stmt = select(MaterializationRun)
        stmt = _filter_runs(stmt, corpus_id, chunking_configuration_id)
        stmt = (
            stmt.order_by(
                MaterializationRun.created_at.desc(), MaterializationRun.id.desc()
            )
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.scalars(stmt)
        return result.all()

    async def count(
        self,
        *,
        corpus_id: uuid.UUID | None = None,
        chunking_configuration_id: uuid.UUID | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(MaterializationRun)
        stmt = _filter_runs(stmt, corpus_id, chunking_configuration_id)
        return await self.session.scalar(stmt) or 0


def _filter_runs(
    stmt: Select[Any],
    corpus_id: uuid.UUID | None,
    chunking_configuration_id: uuid.UUID | None,
) -> Select[Any]:
    """Apply the shared history filters, so listing and counting cannot drift apart."""
    if corpus_id is not None:
        stmt = stmt.where(MaterializationRun.corpus_id == corpus_id)
    if chunking_configuration_id is not None:
        stmt = stmt.where(
            MaterializationRun.chunking_configuration_id == chunking_configuration_id
        )
    return stmt
