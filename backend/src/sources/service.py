from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.get_or_create import get_or_create
from src.infrastructure.database.enums import (
    AuthMethod,
    FileOutcome,
    ImportStatus,
    SourceType,
)
from src.sources.models import (
    ImportFileResult,
    ImportRun,
    ImportSelection,
    SourceConnection,
)
from src.sources.repository import (
    ImportFileResultRepository,
    ImportRunRepository,
    ImportSelectionRepository,
    SourceConnectionRepository,
)

# Identity of the singleton connection manual uploads are attributed to. Uploads are not a
# special case in the data model but a connection like any other, so the day an S3 source
# arrives the provenance query and the import summary keep working unchanged.
UPLOAD_CONNECTION_NAME = "Manual upload"
UPLOAD_SELECTION_NAME = "Manual upload"

# Outcomes that mean the file did reach the platform; the rest are reported but tolerated
_SUCCESS_OUTCOMES = (FileOutcome.IMPORTED, FileOutcome.SKIPPED_DUPLICATE)


class UploadImportService:
    """Import runs of the manual upload source.

    A manual upload is a degenerate import: the file is already in the request body, so
    there is nothing to enumerate and nothing to resume. It therefore runs synchronously
    and never reaches Temporal, which is reserved for long, restartable work with remote
    enumeration. The run is still recorded, because the per-file summary (RF-S07) and the
    provenance (RF-S05) are the same for every source and the UI reads one shape only.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.connections = SourceConnectionRepository(session)
        self.selections = ImportSelectionRepository(session)
        self.runs = ImportRunRepository(session)
        self.file_results = ImportFileResultRepository(session)

    async def get_or_create_selection(self) -> ImportSelection:
        """Return the singleton upload selection, creating it and its connection if absent.

        Idempotent on `(type, name)` and `(connection_id, name)`, so the startup seed can
        run at every boot without duplicating rows or invalidating the provenances that
        already point at the connection.
        """
        connection = await self._get_or_create_connection()

        async def create() -> ImportSelection:
            selection = self.selections.add(
                ImportSelection(
                    connection_id=connection.id,
                    name=UPLOAD_SELECTION_NAME,
                    # An upload selects nothing remotely: the empty, non-recursive
                    # selection is the honest representation of "the caller chose the files".
                    paths=[],
                    recursive=False,
                )
            )
            await self.session.flush()
            return selection

        return await get_or_create(
            self.session,
            lookup=lambda: self.selections.get_by_connection_and_name(
                connection.id, UPLOAD_SELECTION_NAME
            ),
            create=create,
        )

    async def open_run(self) -> ImportRun:
        """Start an import run for one upload request.

        Created directly in `running` and with no `workflow_id`: the work happens inside
        this request, so there is no workflow to correlate it with. This is the hook to
        change if large uploads ever need queueing.
        """
        selection = await self.get_or_create_selection()
        run = self.runs.add(
            ImportRun(
                selection_id=selection.id,
                status=ImportStatus.RUNNING,
                started_at=_now(),
            )
        )
        await self.session.flush()
        return run

    def record_file_result(
        self,
        run: ImportRun,
        *,
        source_uri: str,
        outcome: FileOutcome,
        document_id: uuid.UUID | None = None,
        error_reason: str | None = None,
    ) -> ImportFileResult:
        """Record the outcome of a single file of the run.

        Args:
            run: Run the file belongs to.
            source_uri: How the file was named by the caller; the only identity an upload has.
            outcome: Whether the file was imported, skipped, or failed.
            document_id: Document the file resolved to, absent when nothing was created.
            error_reason: Why the file did not make it, for the failed and skipped cases.

        Returns:
            The staged result row; the caller's transaction persists it.
        """
        result = ImportFileResult(
            import_run_id=run.id,
            source_uri=source_uri,
            document_id=document_id,
            outcome=outcome,
            error_reason=error_reason,
        )
        self.file_results.add_all([result])
        return result

    async def close_run(self, run: ImportRun) -> ImportRun:
        """Aggregate the per-file outcomes into the run and mark it finished.

        The counts are recomputed from `import_file_results` instead of being accumulated
        in memory, so the summary cannot drift from the rows it summarises.

        Args:
            run: Run to close.

        Returns:
            The run with `counts`, `status` and `finished_at` written.
        """
        await self.session.flush()
        counts = await self.file_results.count_by_outcome(run.id)

        run.counts = {outcome.value: count for outcome, count in counts.items()}
        run.status = _run_status(counts)
        run.finished_at = _now()
        await self.session.flush()
        return run

    async def _get_or_create_connection(self) -> SourceConnection:
        """Return the singleton `upload` connection."""

        async def create() -> SourceConnection:
            connection = self.connections.add(
                SourceConnection(
                    name=UPLOAD_CONNECTION_NAME,
                    type=SourceType.UPLOAD,
                    auth_method=AuthMethod.NONE,
                )
            )
            await self.session.flush()
            return connection

        return await get_or_create(
            self.session,
            lookup=lambda: self.connections.get_by_type_and_name(
                SourceType.UPLOAD, UPLOAD_CONNECTION_NAME
            ),
            create=create,
        )


def _run_status(counts: dict[FileOutcome, int]) -> ImportStatus:
    """Derive the status of a run from its per-file outcomes.

    A batch where some files made it and some did not is `partial` and not `failed`: the
    documents that were imported exist, and reporting the whole run as a failure would
    invite a retry that re-uploads the files that already succeeded.
    """
    succeeded = sum(counts.get(outcome, 0) for outcome in _SUCCESS_OUTCOMES)
    total = sum(counts.values())
    if total == 0 or succeeded == 0:
        return ImportStatus.FAILED
    if succeeded < total:
        return ImportStatus.PARTIAL
    return ImportStatus.SUCCEEDED


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
