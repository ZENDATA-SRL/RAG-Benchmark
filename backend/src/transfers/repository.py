from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.artifacts.models import Chunk, ChunkResult
from src.documents.models import Document
from src.indexes.models import IndexBuild
from src.infrastructure.database.enums import (
    ArtifactStatus,
    ConfidenceBand,
    EvidenceLinkStatus,
    ExecutionStatus,
    RelevanceGrade,
)
from src.qa_sets.models import EvidenceLink, EvidenceLinkChunk, Question
from src.transfers.models import TransferCandidate, TransferJob, TransferQuestion

# Rows per INSERT: asyncpg caps a statement at 32767 bind parameters, and a candidate row
# binds eleven.
_CANDIDATE_BATCH = 2000


@dataclasses.dataclass(frozen=True)
class PoolChunk:
    """A chunk with the document it belongs to and how many chunks that document has."""

    chunk: Chunk
    document_id: uuid.UUID
    filename: str
    chunk_count: int


@dataclasses.dataclass(frozen=True)
class SourceChunk:
    """A chunk confirmed as evidence in the source configuration."""

    chunk: Chunk
    document_id: uuid.UUID
    chunk_count: int
    relevance: RelevanceGrade


@dataclasses.dataclass(frozen=True)
class CandidateSummary:
    """What the queue shows of a question's candidates before opening it."""

    top_score: float | None
    plausible: int
    preselected: int


class TransferJobRepository:
    """Data access for `transfer_jobs`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, job: TransferJob) -> TransferJob:
        self.session.add(job)
        return job

    async def get_by_id(self, transfer_job_id: uuid.UUID) -> TransferJob | None:
        return await self.session.get(TransferJob, transfer_job_id)

    async def list(
        self, *, qa_set_id: uuid.UUID | None, limit: int, offset: int
    ) -> Sequence[TransferJob]:
        stmt = select(TransferJob).order_by(
            TransferJob.created_at.desc(), TransferJob.id.desc()
        )
        if qa_set_id is not None:
            stmt = stmt.where(TransferJob.qa_set_id == qa_set_id)
        return (await self.session.scalars(stmt.limit(limit).offset(offset))).all()

    async def count(self, *, qa_set_id: uuid.UUID | None) -> int:
        stmt = select(func.count()).select_from(TransferJob)
        if qa_set_id is not None:
            stmt = stmt.where(TransferJob.qa_set_id == qa_set_id)
        return await self.session.scalar(stmt) or 0


class TransferQuestionRepository:
    """Data access for `transfer_questions`, the questions a job ranks."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_many(
        self, transfer_job_id: uuid.UUID, question_ids: Sequence[uuid.UUID]
    ) -> None:
        if not question_ids:
            return
        await self.session.execute(
            pg_insert(TransferQuestion)
            .values(
                [
                    {"transfer_job_id": transfer_job_id, "question_id": question_id}
                    for question_id in question_ids
                ]
            )
            .on_conflict_do_nothing()
        )

    async def get_by_id(
        self, transfer_question_id: uuid.UUID
    ) -> TransferQuestion | None:
        return await self.session.get(TransferQuestion, transfer_question_id)

    async def get(
        self, transfer_job_id: uuid.UUID, question_id: uuid.UUID
    ) -> TransferQuestion | None:
        stmt = select(TransferQuestion).where(
            TransferQuestion.transfer_job_id == transfer_job_id,
            TransferQuestion.question_id == question_id,
        )
        return await self.session.scalar(stmt)

    async def list_with_questions(
        self, transfer_job_id: uuid.UUID
    ) -> list[tuple[TransferQuestion, Question]]:
        """The questions of a job in the order of the set, which is the queue's order."""
        stmt = (
            select(TransferQuestion, Question)
            .join(Question, Question.id == TransferQuestion.question_id)
            .where(TransferQuestion.transfer_job_id == transfer_job_id)
            .order_by(Question.created_at, Question.id)
        )
        return [tuple(row) for row in (await self.session.execute(stmt)).all()]

    async def unfinished_ids(
        self, transfer_job_id: uuid.UUID, *, after_id: uuid.UUID | None, limit: int
    ) -> list[uuid.UUID]:
        """One page of the questions not ranked yet, keyed on the last id seen."""
        stmt = select(TransferQuestion.id).where(
            TransferQuestion.transfer_job_id == transfer_job_id,
            TransferQuestion.status != ExecutionStatus.SUCCEEDED,
        )
        if after_id is not None:
            stmt = stmt.where(TransferQuestion.id > after_id)
        stmt = stmt.order_by(TransferQuestion.id).limit(limit)
        return list((await self.session.scalars(stmt)).all())

    async def reset_running(self, transfer_job_id: uuid.UUID) -> None:
        """Put questions an interrupted attempt left `running` back to `pending`."""
        await self.session.execute(
            update(TransferQuestion)
            .where(
                TransferQuestion.transfer_job_id == transfer_job_id,
                TransferQuestion.status == ExecutionStatus.RUNNING,
            )
            .values(status=ExecutionStatus.PENDING)
        )

    async def count_by_status(
        self, transfer_job_id: uuid.UUID
    ) -> dict[ExecutionStatus, int]:
        stmt = (
            select(TransferQuestion.status, func.count())
            .where(TransferQuestion.transfer_job_id == transfer_job_id)
            .group_by(TransferQuestion.status)
        )
        return dict((await self.session.execute(stmt)).all())


class TransferCandidateRepository:
    """Data access for `transfer_candidates`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace(
        self,
        transfer_job_id: uuid.UUID,
        question_id: uuid.UUID,
        rows: Sequence[dict],
    ) -> None:
        """Write the candidates of a question, replacing those of an earlier attempt."""
        await self.session.execute(
            delete(TransferCandidate).where(
                TransferCandidate.transfer_job_id == transfer_job_id,
                TransferCandidate.question_id == question_id,
            )
        )
        for start in range(0, len(rows), _CANDIDATE_BATCH):
            await self.session.execute(
                pg_insert(TransferCandidate).values(
                    [
                        {
                            "transfer_job_id": transfer_job_id,
                            "question_id": question_id,
                            **row,
                        }
                        for row in rows[start : start + _CANDIDATE_BATCH]
                    ]
                )
            )

    async def for_question(
        self, transfer_job_id: uuid.UUID, question_id: uuid.UUID
    ) -> list[tuple[TransferCandidate, Chunk, uuid.UUID, str]]:
        """Candidates of a question, best first, with their chunk, document and file name."""
        stmt = (
            select(TransferCandidate, Chunk, Document.id, Document.filename)
            .join(Chunk, Chunk.id == TransferCandidate.chunk_id)
            .join(ChunkResult, ChunkResult.id == Chunk.chunk_result_id)
            .join(Document, Document.id == ChunkResult.document_id)
            .where(
                TransferCandidate.transfer_job_id == transfer_job_id,
                TransferCandidate.question_id == question_id,
            )
            .order_by(TransferCandidate.rank)
        )
        return [tuple(row) for row in (await self.session.execute(stmt)).all()]

    async def summaries(
        self, transfer_job_id: uuid.UUID
    ) -> dict[uuid.UUID, CandidateSummary]:
        """Per question: the best score, the plausible candidates and the pre-selected ones."""
        stmt = (
            select(
                TransferCandidate.question_id,
                func.max(TransferCandidate.combined_score),
                func.count().filter(TransferCandidate.confidence != ConfidenceBand.LOW),
                func.count().filter(TransferCandidate.preselected),
            )
            .where(TransferCandidate.transfer_job_id == transfer_job_id)
            .group_by(TransferCandidate.question_id)
        )
        return {
            question_id: CandidateSummary(top, plausible, preselected)
            for question_id, top, plausible, preselected in (
                await self.session.execute(stmt)
            ).all()
        }


class PoolRepository:
    """The chunks a job compares: the evidence in the source and the pool in the target."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def materialised_documents(
        self, chunking_configuration_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
    ) -> set[uuid.UUID]:
        """The documents, among these, with ready chunks under the configuration."""
        if not document_ids:
            return set()
        stmt = select(ChunkResult.document_id).where(
            ChunkResult.chunking_configuration_id == chunking_configuration_id,
            ChunkResult.document_id.in_(document_ids),
            ChunkResult.status == ArtifactStatus.READY,
        )
        return set((await self.session.scalars(stmt)).all())

    async def pool(
        self, chunking_configuration_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
    ) -> list[PoolChunk]:
        """Every chunk of some documents under a configuration, in reading order."""
        if not document_ids:
            return []
        stmt = (
            select(Chunk, Document.id, Document.filename, ChunkResult.chunk_count)
            .join(ChunkResult, ChunkResult.id == Chunk.chunk_result_id)
            .join(Document, Document.id == ChunkResult.document_id)
            .where(
                ChunkResult.chunking_configuration_id == chunking_configuration_id,
                ChunkResult.document_id.in_(document_ids),
                ChunkResult.status == ArtifactStatus.READY,
            )
            .order_by(Document.filename, Document.id, Chunk.ordinal)
        )
        return [PoolChunk(*row) for row in (await self.session.execute(stmt)).all()]

    async def confirmed_chunks(
        self, question_id: uuid.UUID, chunking_configuration_id: uuid.UUID
    ) -> list[SourceChunk]:
        """The evidence chunks of a question confirmed under a configuration."""
        stmt = (
            select(
                Chunk,
                ChunkResult.document_id,
                ChunkResult.chunk_count,
                EvidenceLinkChunk.relevance,
            )
            .join(EvidenceLinkChunk, EvidenceLinkChunk.chunk_id == Chunk.id)
            .join(EvidenceLink, EvidenceLink.id == EvidenceLinkChunk.evidence_link_id)
            .join(ChunkResult, ChunkResult.id == Chunk.chunk_result_id)
            .where(
                EvidenceLink.question_id == question_id,
                EvidenceLink.chunking_configuration_id == chunking_configuration_id,
                EvidenceLink.status == EvidenceLinkStatus.CONFIRMED,
            )
            .order_by(ChunkResult.document_id, Chunk.ordinal)
        )
        return [SourceChunk(*row) for row in (await self.session.execute(stmt)).all()]

    async def latest_embedding_profile(
        self, chunking_configuration_id: uuid.UUID
    ) -> uuid.UUID | None:
        """The embedder of the newest ready index built on a configuration, if any."""
        stmt = (
            select(IndexBuild.embedding_profile_id)
            .where(
                IndexBuild.chunking_configuration_id == chunking_configuration_id,
                IndexBuild.status == ArtifactStatus.READY,
            )
            .order_by(IndexBuild.created_at.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)
