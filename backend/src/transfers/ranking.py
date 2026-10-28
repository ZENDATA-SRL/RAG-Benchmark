from __future__ import annotations

import asyncio
import dataclasses
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DomainError
from src.infrastructure.database.enums import (
    ConfidenceBand,
    ExecutionStatus,
    TransferStatus,
)
from src.pipelines.service import ProfileService
from src.qa_sets.repository import QuestionRepository
from src.retrieval.embedders import resolve_embedder
from src.retrieval.exceptions import RetrievalBackendError
from src.retrieval.repository import RetrievalRepository
from src.transfers.exceptions import TransferJobNotFoundError
from src.transfers.matching import (
    LEXICAL,
    POSITIONAL,
    SEMANTIC,
    Position,
    band,
    combine,
    cosine,
    keyword_overlap,
    passage_similarity,
    positional_score,
    preselect,
    relative_position,
)
from src.transfers.models import TransferJob, TransferQuestion
from src.transfers.repository import (
    PoolChunk,
    PoolRepository,
    SourceChunk,
    TransferCandidateRepository,
    TransferJobRepository,
    TransferQuestionRepository,
)
from src.transfers.service import TransferService

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class RankOutcome:
    """What happened to one question: ranked with its candidate count, or failed."""

    status: ExecutionStatus
    candidate_count: int = 0
    error: str | None = None


def _position(chunk, document_id: uuid.UUID, chunk_count: int) -> Position:
    page = chunk.chunk_metadata.get("page")
    return Position(
        document_id=document_id,
        page=page if isinstance(page, int) else None,
        relative=relative_position(chunk.ordinal, chunk_count),
    )


class TransferRanker:
    """Rank the candidate chunks of the questions of a job; what the worker calls.

    One question at a time, which is also the unit a relaunched job resumes from: a
    question whose candidates were written is never ranked again.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.jobs = TransferJobRepository(session)
        self.job_questions = TransferQuestionRepository(session)
        self.candidates = TransferCandidateRepository(session)
        self.pool = PoolRepository(session)
        self.questions = QuestionRepository(session)

    async def open_job(self, transfer_job_id: uuid.UUID) -> None:
        """Mark a job `running` for this attempt; questions left `running` go back to pending."""
        job = await self._job(transfer_job_id)
        job.status = TransferStatus.RUNNING
        job.error = None
        await self.job_questions.reset_running(job.id)
        await self.session.flush()

    async def unfinished_ids(
        self, transfer_job_id: uuid.UUID, *, after_id: uuid.UUID | None, limit: int
    ) -> list[uuid.UUID]:
        return await self.job_questions.unfinished_ids(
            transfer_job_id, after_id=after_id, limit=limit
        )

    async def rank(self, transfer_question_id: uuid.UUID) -> RankOutcome:
        """Rank every chunk of the question's gold documents in the target configuration.

        The pool is the whole of those documents, without a cutoff: the right chunk must be
        in the list even when the signals put it low. Each candidate gets the semantic
        signal (cosine with the reference, through the job's embedder), the lexical one and,
        in a transfer, the positional one; they combine with the job's weights into a score,
        a confidence band and, only for a near-identical copy of a source chunk, a
        pre-selection.

        A failure of the embedder is raised so the workflow retries it; any other domain
        error fails only this question.

        Raises:
            RetrievalBackendError: If the embedder failed.
        """
        item = await self.job_questions.get_by_id(transfer_question_id)
        if item is None:
            raise TransferJobNotFoundError(transfer_question_id)
        if item.status == ExecutionStatus.SUCCEEDED:
            return RankOutcome(ExecutionStatus.SUCCEEDED, item.candidate_count)
        job = await self._job(item.transfer_job_id)
        item.status = ExecutionStatus.RUNNING
        await self.session.flush()
        try:
            rows = await self._rank_rows(job, item)
        except RetrievalBackendError:
            raise
        except DomainError as error:
            return await self.fail(item.id, error.message)
        await self.candidates.replace(job.id, item.question_id, rows)
        item.status = ExecutionStatus.SUCCEEDED
        item.candidate_count = len(rows)
        item.error = None
        await self.session.flush()
        return RankOutcome(ExecutionStatus.SUCCEEDED, len(rows))

    async def fail(self, transfer_question_id: uuid.UUID, error: str) -> RankOutcome:
        """Mark a question `failed` with its reason; the job goes on with the others."""
        item = await self.job_questions.get_by_id(transfer_question_id)
        if item is None:
            raise TransferJobNotFoundError(transfer_question_id)
        item.status = ExecutionStatus.FAILED
        item.error = error
        await self.session.flush()
        return RankOutcome(ExecutionStatus.FAILED, error=error)

    async def record_progress(self, transfer_job_id: uuid.UUID) -> None:
        """Copy the progress and the recall ceiling onto the job row."""
        job = await self._job(transfer_job_id)
        view = await TransferService(self.session).view(job)
        job.progress = {**job.progress, **dataclasses.asdict(view.progress)}
        job.recall_ceiling = view.recall_ceiling
        await self.session.flush()

    async def finish_job(self, transfer_job_id: uuid.UUID) -> None:
        """Close a job whose questions were all attempted; failed ones can be resumed."""
        await self.record_progress(transfer_job_id)
        job = await self._job(transfer_job_id)
        if job.status != TransferStatus.CANCELLED:
            job.status = TransferStatus.COMPLETED
        await self.session.flush()

    async def fail_job(self, transfer_job_id: uuid.UUID, reason: str) -> None:
        """Record that a job stopped for a reason that is not one of its questions."""
        job = await self._job(transfer_job_id)
        job.status = TransferStatus.FAILED
        job.error = reason
        await self.session.flush()

    async def _job(self, transfer_job_id: uuid.UUID) -> TransferJob:
        job = await self.jobs.get_by_id(transfer_job_id)
        if job is None:
            raise TransferJobNotFoundError(transfer_job_id)
        return job

    async def _rank_rows(self, job: TransferJob, item: TransferQuestion) -> list[dict]:
        question = (await self.questions.list_by_ids([item.question_id]))[0]
        gold = (await self.questions.gold_by_question([question.id])).get(
            question.id, []
        )
        pool = await self.pool.pool(
            job.target_configuration_id, [document_id for document_id, _ in gold]
        )
        if not pool:
            return []
        sources: list[SourceChunk] = []
        if job.source_configuration_id is not None:
            sources = await self.pool.confirmed_chunks(
                question.id, job.source_configuration_id
            )
            references = [source.chunk.text for source in sources]
        else:
            answers = (await self.questions.answers_by_question([question.id])).get(
                question.id, []
            )
            references = [
                " ".join([question.text, answers[0].text if answers else ""]).strip()
            ]
        semantic = await self._semantic(job, references, pool)
        source_positions = [
            _position(source.chunk, source.document_id, source.chunk_count)
            for source in sources
        ]
        weights = job.signal_weights
        thresholds = job.confidence_thresholds

        rows = []
        for index, candidate in enumerate(pool):
            if sources:
                matches = [
                    passage_similarity(source.chunk.text, candidate.chunk.text)
                    for source in sources
                ]
                best = max(range(len(sources)), key=lambda i: matches[i])
                lexical = matches[best]
                positional = positional_score(
                    _position(
                        candidate.chunk, candidate.document_id, candidate.chunk_count
                    ),
                    source_positions,
                )
                suggested = sources[best].relevance if lexical > 0 else None
            else:
                lexical = keyword_overlap(references[0], candidate.chunk.text)
                positional = None
                suggested = None
            scores = {
                SEMANTIC: semantic[index] if semantic is not None else None,
                LEXICAL: lexical,
                POSITIONAL: positional,
            }
            combined = combine(scores, weights)
            chosen = preselect(lexical, has_source=bool(sources), thresholds=thresholds)
            rows.append(
                {
                    "chunk_id": candidate.chunk.id,
                    "combined_score": combined,
                    "semantic_score": scores[SEMANTIC],
                    "lexical_score": lexical,
                    "positional_score": positional,
                    # A near-identical copy is the surest candidate, whatever the
                    # other signals say: an embedder can disagree with an exact match.
                    "confidence": ConfidenceBand.HIGH
                    if chosen
                    else band(combined, thresholds),
                    "preselected": chosen,
                    "suggested_relevance": suggested,
                }
            )
        rows.sort(
            key=lambda row: (row["preselected"], row["combined_score"]), reverse=True
        )
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
        return rows

    async def _semantic(
        self, job: TransferJob, references: list[str], pool: list[PoolChunk]
    ) -> list[float] | None:
        """Best cosine of each candidate with any reference, or `None` without an embedder."""
        if job.embedding_profile_id is None or not references:
            return None
        profile = await ProfileService(self.session).get_embedding_profile(
            job.embedding_profile_id
        )
        key = await RetrievalRepository(self.session).component_key(
            profile.component_version_id
        )
        if key is None:
            return None
        texts = references + [candidate.chunk.text for candidate in pool]
        try:
            vectors = await asyncio.to_thread(_embed, key, dict(profile.params), texts)
        except Exception as error:
            logger.exception("transfer embedding failed")
            raise RetrievalBackendError(
                "embedding", str(error) or type(error).__name__
            ) from error
        reference_vectors = vectors[: len(references)]
        return [
            max(cosine(reference, vector) for reference in reference_vectors)
            for vector in vectors[len(references) :]
        ]


def _embed(key: str, params: dict, texts: list[str]) -> list[list[float]]:
    return resolve_embedder(key, params).embed_documents(texts)
