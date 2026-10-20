from __future__ import annotations

import dataclasses
import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.artifacts.repository import ChunkResultRepository
from src.core.get_or_create import get_or_create
from src.corpora.repository import CorpusDocumentRepository
from src.corpora.service import CorpusService
from src.documents.repository import DocumentRepository
from src.infrastructure.database.enums import (
    TERMINAL_ARTIFACT_STATUSES,
    ArtifactStatus,
    DocumentStatus,
)
from src.infrastructure.temporal import WorkflowClient
from src.infrastructure.temporal.workflow_ids import (
    CHUNKING_TASK_QUEUE,
    MATERIALIZE_CHUNKS_WORKFLOW,
    materialize_workflow_id,
)
from src.materializations.exceptions import (
    DocumentsNotStoredError,
    EmptyMaterializationError,
    MaterializationNotCancellableError,
    MaterializationRunNotFoundError,
)
from src.materializations.models import MaterializationRun
from src.materializations.repository import MaterializationRunRepository
from src.pipelines.service import ChunkingConfigurationService

# Default child-workflow concurrency of a run; mirrors the workflow's own default so the API
# and the worker cannot disagree about what "no concurrency given" means.
DEFAULT_MATERIALIZATION_CONCURRENCY = 5

# Upper bound on the failures reported with a run: the list explains a failure, it is not a
# report, and the per-document detail is always available from the chunk-result endpoints.
_MAX_REPORTED_FAILURES = 50

CANCELLED_REASON = "cancelled"


@dataclasses.dataclass(frozen=True)
class DocumentFailure:
    """Why one document of a run did not produce chunks."""

    document_id: uuid.UUID
    error: str | None


@dataclasses.dataclass(frozen=True)
class MaterializationLaunch:
    """A launched materialisation and whether this request is what started it."""

    run: MaterializationRun
    started: bool


class MaterializationRunService:
    """The denormalised progress of a user-triggered chunk materialisation (RT-O07).

    Reads and writes the run row and the artefacts it summarises, and nothing else:
    following a run must not depend on Temporal being reachable, which is the whole reason
    the row exists.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.runs = MaterializationRunRepository(session)
        self.chunk_results = ChunkResultRepository(session)
        self.corpus_documents = CorpusDocumentRepository(session)

    async def open_run(
        self,
        *,
        workflow_id: str,
        chunking_configuration_id: uuid.UUID,
        document_count: int,
        corpus_id: uuid.UUID | None = None,
    ) -> MaterializationRun:
        """Return the run for a workflow id, creating it as `running` if absent.

        Get-or-create on `workflow_id` so a workflow retried or continued-as-new reuses the
        same row instead of forking the progress the UI reads: a run still in flight is
        returned untouched, because its progress is authoritative for what already happened.

        A row that already reached a terminal state is reset instead. The workflow id is a
        function of the configuration and the document set, so relaunching the same work
        after a failure or a cancellation lands on the same row; leaving it terminal would
        show `cancelled` while a new workflow is running.
        """

        async def create() -> MaterializationRun:
            run = self.runs.add(
                MaterializationRun(
                    workflow_id=workflow_id,
                    chunking_configuration_id=chunking_configuration_id,
                    corpus_id=corpus_id,
                    document_count=document_count,
                    status=ArtifactStatus.RUNNING,
                    progress={
                        "ready": 0,
                        "failed": 0,
                        "cached": 0,
                        "pending": document_count,
                    },
                    started_at=dt.datetime.now(dt.UTC),
                )
            )
            await self.session.flush()
            return run

        run = await get_or_create(
            self.session,
            lookup=lambda: self.runs.get_by_workflow_id(workflow_id),
            create=create,
        )
        if run.status in TERMINAL_ARTIFACT_STATUSES:
            run.status = ArtifactStatus.RUNNING
            run.document_count = document_count
            run.progress = {
                "ready": 0,
                "failed": 0,
                "cached": 0,
                "pending": document_count,
            }
            run.error = None
            run.started_at = dt.datetime.now(dt.UTC)
            run.finished_at = None
            await self.session.flush()
        return run

    async def update_progress(
        self, *, workflow_id: str, progress: dict[str, int]
    ) -> MaterializationRun | None:
        """Overwrite a run's progress counters with the workflow's current tally.

        The workflow owns the counts and passes the whole tally each time, so the write is
        idempotent and stays monotonic as long as the caller only ever grows them; `pending`
        is derived so the four numbers always sum to `document_count`.
        """
        run = await self.runs.get_by_workflow_id(workflow_id)
        if run is None:
            return None
        done = (
            progress.get("ready", 0)
            + progress.get("failed", 0)
            + progress.get("cached", 0)
        )
        run.progress = {
            "ready": progress.get("ready", 0),
            "failed": progress.get("failed", 0),
            "cached": progress.get("cached", 0),
            "pending": max(run.document_count - done, 0),
        }
        await self.session.flush()
        return run

    async def complete_run(
        self, *, workflow_id: str, progress: dict[str, int]
    ) -> MaterializationRun | None:
        """Mark a run finished with its final tally, `ready` unless any document failed."""
        run = await self.update_progress(workflow_id=workflow_id, progress=progress)
        if run is None:
            return None
        run.status = (
            ArtifactStatus.FAILED if run.progress["failed"] else ArtifactStatus.READY
        )
        run.finished_at = dt.datetime.now(dt.UTC)
        await self.session.flush()
        return run

    async def get(self, run_id: uuid.UUID) -> MaterializationRun:
        """Return a run by id.

        Raises:
            MaterializationRunNotFoundError: If it does not exist.
        """
        run = await self.runs.get_by_id(run_id)
        if run is None:
            raise MaterializationRunNotFoundError(run_id)
        return run

    async def list(
        self,
        *,
        corpus_id: uuid.UUID | None = None,
        chunking_configuration_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[MaterializationRun], int]:
        """One page of run history, newest first, and the size of the whole set."""
        runs = await self.runs.list(
            corpus_id=corpus_id,
            chunking_configuration_id=chunking_configuration_id,
            limit=limit,
            offset=offset,
        )
        total = await self.runs.count(
            corpus_id=corpus_id, chunking_configuration_id=chunking_configuration_id
        )
        return runs, total

    async def failures(self, run: MaterializationRun) -> list[DocumentFailure]:
        """Documents that failed under the run's configuration, with their reason.

        Read from `chunk_results` and not from a column of the run: the outcome of a document
        is a property of its artefact, and duplicating it here would create a second
        truth that a re-materialisation would leave stale. When the run has a corpus the list
        is scoped to it; a run launched on explicit ids is a preview of a few files, so the
        configuration's failures are the same set in practice.
        """
        document_ids = (
            await self.corpus_documents.list_document_ids(run.corpus_id)
            if run.corpus_id is not None
            else None
        )
        failed = await self.chunk_results.list_failed(
            run.chunking_configuration_id,
            document_ids=document_ids,
            limit=_MAX_REPORTED_FAILURES,
        )
        return [
            DocumentFailure(document_id=result.document_id, error=result.error)
            for result in failed
        ]


class MaterializationService:
    """Launch and cancel a chunk materialisation over a set of documents.

    The same entry point serves the preview on a handful of files (RF-P08) and a whole
    corpus, exactly as the same workflow does: the difference is the size of the document
    list, not the code path, so what the user previews is what the corpus run will produce.
    Reading a run's progress belongs to `MaterializationRunService`, which needs no Temporal
    connection.
    """

    def __init__(self, session: AsyncSession, workflows: WorkflowClient) -> None:
        self.session = session
        self.workflows = workflows
        self.runs = MaterializationRunService(session)
        self.configurations = ChunkingConfigurationService(session)
        self.documents = DocumentRepository(session)
        self.corpus_documents = CorpusDocumentRepository(session)

    async def start(
        self,
        *,
        chunking_configuration_id: uuid.UUID,
        document_ids: Sequence[uuid.UUID] | None = None,
        corpus_id: uuid.UUID | None = None,
        concurrency: int | None = None,
    ) -> MaterializationLaunch:
        """Start a materialisation, or return the run already doing the same work.

        The workflow id is a function of the configuration and the document *set*, so a
        second identical request is refused by Temporal itself and reported as the existing
        run: a double click on the launch button is not a user error (RT-O01).

        Args:
            chunking_configuration_id: Configuration to materialise.
            document_ids: Explicit documents; when omitted, every document of `corpus_id`.
            corpus_id: Corpus the run belongs to, recorded for the UI and used to resolve the
                documents when none are given explicitly.
            concurrency: Maximum number of documents processed at once.

        Returns:
            The run row and whether this call started the workflow.

        Raises:
            ChunkingConfigurationNotFoundError: If the configuration does not exist.
            CorpusNotFoundError: If `corpus_id` does not exist.
            EmptyMaterializationError: If no document was resolved.
            DocumentsNotStoredError: If any resolved document is not `stored`.
        """
        await self.configurations.get(chunking_configuration_id)
        resolved = await self._resolve_documents(document_ids, corpus_id)

        workflow_id = materialize_workflow_id(chunking_configuration_id, resolved)
        run = await self.runs.open_run(
            workflow_id=workflow_id,
            chunking_configuration_id=chunking_configuration_id,
            document_count=len(resolved),
            corpus_id=corpus_id,
        )
        outcome = await self.workflows.start(
            MATERIALIZE_CHUNKS_WORKFLOW,
            arg={
                "document_ids": [str(document_id) for document_id in resolved],
                "chunking_configuration_id": str(chunking_configuration_id),
                "corpus_id": str(corpus_id) if corpus_id else None,
                "max_concurrency": concurrency or DEFAULT_MATERIALIZATION_CONCURRENCY,
            },
            workflow_id=workflow_id,
            task_queue=CHUNKING_TASK_QUEUE,
        )
        return MaterializationLaunch(run=run, started=outcome.started)

    async def cancel(self, run_id: uuid.UUID) -> MaterializationRun:
        """Cancel a running materialisation, recording `cancelled` as its reason.

        Not required by the requirements for chunking (RF-E08 is about experiments), but a
        user who launched a chunking over two hundred wrong files looks for this immediately.

        Raises:
            MaterializationRunNotFoundError: If the run does not exist.
            MaterializationNotCancellableError: If the run already reached a terminal state.
        """
        run = await self.runs.get(run_id)
        if run.status in TERMINAL_ARTIFACT_STATUSES:
            raise MaterializationNotCancellableError(run_id, run.status)

        await self.workflows.cancel(run.workflow_id)
        # Marked terminal here rather than waiting for the workflow's own summary activity:
        # a cancelled workflow may never run one, and a run stuck on `running` forever is
        # worse than one that says it was cancelled.
        run.status = ArtifactStatus.FAILED
        run.error = CANCELLED_REASON
        run.finished_at = dt.datetime.now(dt.UTC)
        await self.session.flush()
        return run

    async def _resolve_documents(
        self, document_ids: Sequence[uuid.UUID] | None, corpus_id: uuid.UUID | None
    ) -> list[uuid.UUID]:
        """Resolve and validate the document set a run will cover.

        Every document must be `stored`: parsing something still being fetched would produce
        an artefact keyed on a content hash that is not final yet.
        """
        if document_ids:
            resolved = list(dict.fromkeys(document_ids))
        else:
            if corpus_id is None:
                raise EmptyMaterializationError()
            await CorpusService(self.session).get(corpus_id)
            resolved = list(await self.corpus_documents.list_document_ids(corpus_id))

        if not resolved:
            raise EmptyMaterializationError()

        found = await self.documents.list_by_ids(resolved)
        by_id = {document.id: document for document in found}
        offending = {
            str(document_id): (
                by_id[document_id].status.value if document_id in by_id else "unknown"
            )
            for document_id in resolved
            if document_id not in by_id
            or by_id[document_id].status is not DocumentStatus.STORED
        }
        if offending:
            raise DocumentsNotStoredError(offending)
        return resolved
