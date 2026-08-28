from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.enums import FileOutcome, SourceType
from src.sources.models import (
    DocumentProvenance,
    ImportFileResult,
    ImportRun,
    ImportSelection,
    SourceConnection,
)


class SourceConnectionRepository:
    """Data access for `source_connections`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, connection: SourceConnection) -> SourceConnection:
        self.session.add(connection)
        return connection

    async def get_by_id(self, connection_id: uuid.UUID) -> SourceConnection | None:
        return await self.session.get(SourceConnection, connection_id)

    async def get_by_type_and_name(
        self, connection_type: SourceType, name: str
    ) -> SourceConnection | None:
        """Look up a connection by the pair the upload seed treats as its identity."""
        stmt = select(SourceConnection).where(
            SourceConnection.type == connection_type,
            SourceConnection.name == name,
        )
        return await self.session.scalar(stmt)

    async def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[SourceConnection]:
        stmt = select(SourceConnection).order_by(SourceConnection.name).limit(limit).offset(offset)
        result = await self.session.scalars(stmt)
        return result.all()

    async def delete(self, connection: SourceConnection) -> None:
        await self.session.delete(connection)


class ImportSelectionRepository:
    """Data access for `import_selections`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, selection: ImportSelection) -> ImportSelection:
        self.session.add(selection)
        return selection

    async def get_by_id(self, selection_id: uuid.UUID) -> ImportSelection | None:
        return await self.session.get(ImportSelection, selection_id)

    async def get_by_connection_and_name(
        self, connection_id: uuid.UUID, name: str
    ) -> ImportSelection | None:
        """Look up a selection by name within its connection, for idempotent seeding."""
        stmt = select(ImportSelection).where(
            ImportSelection.connection_id == connection_id,
            ImportSelection.name == name,
        )
        return await self.session.scalar(stmt)

    async def list_by_connection(self, connection_id: uuid.UUID) -> Sequence[ImportSelection]:
        stmt = (
            select(ImportSelection)
            .where(ImportSelection.connection_id == connection_id)
            .order_by(ImportSelection.name)
        )
        result = await self.session.scalars(stmt)
        return result.all()


class ImportRunRepository:
    """Data access for `import_runs`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, run: ImportRun) -> ImportRun:
        self.session.add(run)
        return run

    async def get_by_id(self, run_id: uuid.UUID) -> ImportRun | None:
        return await self.session.get(ImportRun, run_id)

    async def get_by_workflow_id(self, workflow_id: str) -> ImportRun | None:
        """Resolve a run from its deterministic Temporal workflow id (idempotent start)."""
        stmt = select(ImportRun).where(ImportRun.workflow_id == workflow_id)
        return await self.session.scalar(stmt)

    async def list_by_selection(
        self, selection_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> Sequence[ImportRun]:
        stmt = (
            select(ImportRun)
            .where(ImportRun.selection_id == selection_id)
            .order_by(ImportRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.scalars(stmt)
        return result.all()


class ImportFileResultRepository:
    """Data access for `import_file_results`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_all(self, results: Iterable[ImportFileResult]) -> None:
        self.session.add_all(list(results))

    async def list_by_run(
        self,
        import_run_id: uuid.UUID,
        *,
        outcome: FileOutcome | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ImportFileResult]:
        """List per-file outcomes of a run, optionally filtered by outcome."""
        stmt = select(ImportFileResult).where(ImportFileResult.import_run_id == import_run_id)
        if outcome is not None:
            stmt = stmt.where(ImportFileResult.outcome == outcome)
        stmt = stmt.order_by(ImportFileResult.source_uri).limit(limit).offset(offset)
        result = await self.session.scalars(stmt)
        return result.all()

    async def count_by_outcome(self, import_run_id: uuid.UUID) -> dict[FileOutcome, int]:
        """Aggregate the run outcomes, used to refresh `import_runs.counts`."""
        stmt = (
            select(ImportFileResult.outcome, func.count())
            .where(ImportFileResult.import_run_id == import_run_id)
            .group_by(ImportFileResult.outcome)
        )
        rows = await self.session.execute(stmt)
        return {outcome: count for outcome, count in rows.all()}


class DocumentProvenanceRepository:
    """Data access for `document_provenances`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, provenance: DocumentProvenance) -> DocumentProvenance:
        self.session.add(provenance)
        return provenance

    async def get_by_natural_key(
        self, document_id: uuid.UUID, connection_id: uuid.UUID, original_uri: str
    ) -> DocumentProvenance | None:
        """Check whether a provenance already exists, to keep re-syncs idempotent."""
        stmt = select(DocumentProvenance).where(
            DocumentProvenance.document_id == document_id,
            DocumentProvenance.connection_id == connection_id,
            DocumentProvenance.original_uri == original_uri,
        )
        return await self.session.scalar(stmt)

    async def list_by_document(self, document_id: uuid.UUID) -> Sequence[DocumentProvenance]:
        stmt = (
            select(DocumentProvenance)
            .where(DocumentProvenance.document_id == document_id)
            .order_by(DocumentProvenance.created_at)
        )
        result = await self.session.scalars(stmt)
        return result.all()
