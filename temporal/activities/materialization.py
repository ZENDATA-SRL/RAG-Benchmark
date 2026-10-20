from __future__ import annotations

import dataclasses
import uuid

from src.artifacts.service import ArtefactService
from src.corpora.repository import CorpusSnapshotRepository
from src.materializations.service import MaterializationRunService
from temporalio import activity

from temporal.config import activity_session


@activity.defn
async def open_materialization_run(
    workflow_id: str,
    chunking_configuration_id: str,
    document_count: int,
    corpus_id: str | None,
) -> str:
    """Create (or reuse) the denormalised run row and return its id (RT-O07)."""
    async with activity_session() as session:
        run = await MaterializationRunService(session).open_run(
            workflow_id=workflow_id,
            chunking_configuration_id=uuid.UUID(chunking_configuration_id),
            document_count=document_count,
            corpus_id=uuid.UUID(corpus_id) if corpus_id else None,
        )
        return str(run.id)


@activity.defn
async def documents_needing_chunking(
    document_ids: list[str], chunking_configuration_id: str
) -> list[str]:
    """Return the subset of documents without a ready chunk result for the configuration.

    This is what makes growing a corpus cheap: only the new documents are chunked (RF-C05).
    """
    async with activity_session() as session:
        needing = await ArtefactService(session).documents_needing_chunking(
            [uuid.UUID(document_id) for document_id in document_ids],
            uuid.UUID(chunking_configuration_id),
        )
        return [str(document_id) for document_id in needing]


@dataclasses.dataclass
class SnapshotDocumentsPage:
    """One page of a snapshot: how many documents were scanned and which need chunking."""

    scanned: int
    needing: list[str]


@activity.defn
async def snapshot_documents_needing_chunking(
    corpus_snapshot_id: str, chunking_configuration_id: str, offset: int, limit: int
) -> SnapshotDocumentsPage:
    """Return the documents of one snapshot page that still need chunking.

    Paging lives here so a workflow over a large snapshot never carries the whole list of
    document ids in its input or history, which would exceed the payload limit.
    """
    async with activity_session() as session:
        document_ids = await CorpusSnapshotRepository(
            session
        ).list_snapshot_document_ids(
            uuid.UUID(corpus_snapshot_id), limit=limit, offset=offset
        )
        needing = await ArtefactService(session).documents_needing_chunking(
            list(document_ids), uuid.UUID(chunking_configuration_id)
        )
        return SnapshotDocumentsPage(
            scanned=len(document_ids),
            needing=[str(document_id) for document_id in needing],
        )


@activity.defn
async def record_progress(workflow_id: str, progress: dict[str, int]) -> None:
    """Write the workflow's current tally onto the run row for the UI to poll (RT-U05)."""
    async with activity_session() as session:
        await MaterializationRunService(session).update_progress(
            workflow_id=workflow_id, progress=progress
        )


@activity.defn
async def summarize_run(workflow_id: str, progress: dict[str, int]) -> None:
    """Finalise the run row with its terminal status and finish time."""
    async with activity_session() as session:
        await MaterializationRunService(session).complete_run(
            workflow_id=workflow_id, progress=progress
        )
