from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Mapping, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.enums import (
    EvidenceLinkStatus,
    ExecutionStatus,
    TransferStatus,
)
from src.infrastructure.temporal import WorkflowClient
from src.infrastructure.temporal.workflow_ids import (
    EXPERIMENTS_TASK_QUEUE,
    TRANSFER_DATASET_WORKFLOW,
    transfer_dataset_workflow_id,
)
from src.pipelines.service import ChunkingConfigurationService, ProfileService
from src.qa_sets.models import Question
from src.qa_sets.repository import EvidenceRepository, QuestionRepository
from src.qa_sets.service import NOT_REVIEWED, QASetService
from src.transfers.exceptions import (
    NothingToTransferError,
    QuestionNotInTransferError,
    SameConfigurationError,
    TransferJobNotFoundError,
    TransferNotCancellableError,
    TransferNotResumableError,
    UncoveredQuestionsChoiceRequiredError,
)
from src.transfers.matching import DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS
from src.transfers.models import TransferCandidate, TransferJob
from src.transfers.repository import (
    CandidateSummary,
    PoolRepository,
    SourceChunk,
    TransferCandidateRepository,
    TransferJobRepository,
    TransferQuestionRepository,
)

# Questions ranked at once by the worker: each embeds its candidates, and the embedder is
# rate limited.
DEFAULT_TRANSFER_CONCURRENCY = 4

# Where a question stands in the review queue.
PENDING = "pending"
FAILED = "failed"
PRESELECTED = "preselected"
TO_REVIEW = "to_review"
NO_CANDIDATES = "no_candidates"
DECIDED = "decided"
QUEUE_STATES = (PRESELECTED, TO_REVIEW, NO_CANDIDATES, PENDING, FAILED, DECIDED)
# The states still waiting for a person, in the order the queue offers them: the near
# certain ones first, since they take a second each.
UNDECIDED_STATES = (PRESELECTED, TO_REVIEW, NO_CANDIDATES)

# Why a question of the set is not in a job.
ALREADY_DECIDED = "already_decided"
NOT_CONFIRMED_IN_SOURCE = "not_confirmed_in_source"
NO_GOLD_DOCUMENTS = "no_gold_documents"
DOCUMENTS_NOT_MATERIALISED = "documents_not_materialised"


@dataclasses.dataclass(frozen=True)
class UncoveredQuestion:
    """A question whose candidates cannot be computed in the target configuration."""

    question_id: uuid.UUID
    text: str
    reason: str
    missing_documents: list[tuple[uuid.UUID, str]]


@dataclasses.dataclass(frozen=True)
class TransferProgress:
    """How far the ranking and the human review of a job have gone."""

    total: int
    ranked: int
    failed: int
    reviewed: int
    confirmed: int
    not_found: int


@dataclasses.dataclass(frozen=True)
class TransferView:
    """A job with its live progress and the recall ceiling of its target."""

    job: TransferJob
    progress: TransferProgress
    recall_ceiling: float | None
    excluded: list[UncoveredQuestion] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class QueueRow:
    """A question of a job as listed in the queue."""

    question_id: uuid.UUID
    text: str
    state: str
    evidence_status: str
    top_score: float | None
    plausible: int
    preselected: int
    error: str | None


@dataclasses.dataclass(frozen=True)
class ReviewCandidate:
    """A proposed chunk with what the reviewer needs to judge it."""

    candidate: TransferCandidate
    chunk_text: str
    ordinal: int
    page: int | None
    document_id: uuid.UUID
    filename: str


@dataclasses.dataclass(frozen=True)
class QuestionReview:
    """A question of a job opened for review."""

    question: Question
    state: str
    evidence_status: str
    reference: list[SourceChunk]
    candidates: list[ReviewCandidate]
    next_question_id: uuid.UUID | None


def _page(chunk) -> int | None:
    page = chunk.chunk_metadata.get("page")
    return page if isinstance(page, int) else None


def queue_state(
    ranking: ExecutionStatus, evidence: str, summary: CandidateSummary | None
) -> str:
    """Where a question stands: decided by a person, waiting for one, or not ranked yet."""
    if evidence in (
        EvidenceLinkStatus.CONFIRMED.value,
        EvidenceLinkStatus.NOT_FOUND.value,
    ):
        return DECIDED
    if ranking == ExecutionStatus.FAILED:
        return FAILED
    if ranking != ExecutionStatus.SUCCEEDED:
        return PENDING
    if summary is not None and summary.preselected:
        return PRESELECTED
    if summary is not None and summary.plausible:
        return TO_REVIEW
    return NO_CANDIDATES


class TransferService:
    """Creation of transfer jobs, their progress and their review queue."""

    def __init__(
        self, session: AsyncSession, workflows: WorkflowClient | None = None
    ) -> None:
        self.session = session
        self.workflows = workflows
        self.jobs = TransferJobRepository(session)
        self.job_questions = TransferQuestionRepository(session)
        self.candidates = TransferCandidateRepository(session)
        self.pool = PoolRepository(session)
        self.questions = QuestionRepository(session)
        self.evidence = EvidenceRepository(session)
        self.qa_sets = QASetService(session)

    async def create(
        self,
        *,
        qa_set_id: uuid.UUID,
        target_configuration_id: uuid.UUID,
        source_configuration_id: uuid.UUID | None = None,
        embedding_profile_id: uuid.UUID | None = None,
        signal_weights: Mapping[str, float] | None = None,
        confidence_thresholds: Mapping[str, float] | None = None,
        question_ids: Sequence[uuid.UUID] | None = None,
        exclude_uncovered: bool = False,
        concurrency: int | None = None,
    ) -> TransferView:
        """Create a job proposing evidence chunks in a configuration, and start it.

        The job takes the answerable questions of the set (or of the subset given) that are
        not decided yet in the target: a question confirmed or marked not found there is a
        human decision, and a job never puts it back into question. With a source, only the
        questions confirmed in the source have anything to transfer.

        A question can only be ranked if its gold documents have chunks in the target
        configuration. Those that do not are listed, and the caller must exclude them
        explicitly; otherwise they would look like questions without evidence when they
        were never searched.

        Without an embedding profile, the newest ready index built on the target lends its
        embedder; with none at all, the ranking rests on the lexical and positional signals.

        Raises:
            QASetNotFoundError: If the set does not exist.
            ChunkingConfigurationNotFoundError: If a configuration does not exist.
            ProfileNotFoundError: If the embedding profile does not exist.
            SameConfigurationError: If the source is the target.
            UncoveredQuestionsChoiceRequiredError: If some questions cannot be ranked and
                were not excluded.
            NothingToTransferError: If no question is left.
        """
        await self.qa_sets.get(qa_set_id)
        configurations = ChunkingConfigurationService(self.session)
        await configurations.get(target_configuration_id)
        if source_configuration_id is not None:
            if source_configuration_id == target_configuration_id:
                raise SameConfigurationError(target_configuration_id)
            await configurations.get(source_configuration_id)
        if embedding_profile_id is not None:
            await ProfileService(self.session).get_embedding_profile(
                embedding_profile_id
            )
        else:
            embedding_profile_id = await self.pool.latest_embedding_profile(
                target_configuration_id
            )

        candidates = await self.questions.answerable_ids_by_set(qa_set_id)
        if question_ids is not None:
            wanted = set(question_ids)
            candidates = [item for item in candidates if item in wanted]
        skipped: dict[str, int] = {}
        decided = await self.evidence.statuses(candidates, target_configuration_id)
        included = [
            item
            for item in candidates
            if decided.get(item)
            not in (EvidenceLinkStatus.CONFIRMED, EvidenceLinkStatus.NOT_FOUND)
        ]
        if len(included) < len(candidates):
            skipped[ALREADY_DECIDED] = len(candidates) - len(included)
        if source_configuration_id is not None:
            source = await self.evidence.statuses(included, source_configuration_id)
            confirmed = [
                item
                for item in included
                if source.get(item) == EvidenceLinkStatus.CONFIRMED
            ]
            if len(confirmed) < len(included):
                skipped[NOT_CONFIRMED_IN_SOURCE] = len(included) - len(confirmed)
            included = confirmed

        uncovered = await self._uncovered(included, target_configuration_id)
        if uncovered and not exclude_uncovered:
            raise UncoveredQuestionsChoiceRequiredError(
                [
                    {
                        "question_id": str(item.question_id),
                        "text": item.text,
                        "reason": item.reason,
                        "missing_documents": [
                            {"document_id": str(document_id), "filename": filename}
                            for document_id, filename in item.missing_documents
                        ],
                    }
                    for item in uncovered
                ]
            )
        left_out = {item.question_id for item in uncovered}
        included = [item for item in included if item not in left_out]
        if not included:
            raise NothingToTransferError(
                {**skipped, "uncovered": len(uncovered)} if uncovered else skipped
            )

        job = self.jobs.add(
            TransferJob(
                qa_set_id=qa_set_id,
                source_configuration_id=source_configuration_id,
                target_configuration_id=target_configuration_id,
                embedding_profile_id=embedding_profile_id,
                signal_weights={**DEFAULT_WEIGHTS, **(signal_weights or {})},
                confidence_thresholds={
                    **DEFAULT_THRESHOLDS,
                    **(confidence_thresholds or {}),
                },
                progress={
                    "total": len(included),
                    "skipped": skipped,
                    "excluded": len(uncovered),
                    "concurrency": concurrency or DEFAULT_TRANSFER_CONCURRENCY,
                },
            )
        )
        await self.session.flush()
        job.workflow_id = transfer_dataset_workflow_id(job.id)
        await self.session.flush()
        await self.job_questions.add_many(job.id, included)
        await self._launch(job)
        await self.session.refresh(job)
        return dataclasses.replace(await self.view(job), excluded=uncovered)

    async def get(self, transfer_job_id: uuid.UUID) -> TransferJob:
        """Return a job.

        Raises:
            TransferJobNotFoundError: If it does not exist.
        """
        job = await self.jobs.get_by_id(transfer_job_id)
        if job is None:
            raise TransferJobNotFoundError(transfer_job_id)
        return job

    async def view(self, job: TransferJob) -> TransferView:
        """A job with its progress read live, so a decision shows at once.

        The review happens through the evidence of each question, outside the job, so the
        reviewed counts and the recall ceiling are read from the evidence and never go
        stale. The ceiling is the target configuration's on the whole set: questions
        decided before the job count too.
        """
        counts = await self.job_questions.count_by_status(job.id)
        rows = await self.job_questions.list_with_questions(job.id)
        statuses = await self.evidence.statuses(
            [question.id for _, question in rows], job.target_configuration_id
        )
        confirmed = sum(
            1 for status in statuses.values() if status == EvidenceLinkStatus.CONFIRMED
        )
        not_found = sum(
            1 for status in statuses.values() if status == EvidenceLinkStatus.NOT_FOUND
        )
        coverage = await self.qa_sets.evidence_coverage(
            job.qa_set_id, job.target_configuration_id
        )
        return TransferView(
            job=job,
            progress=TransferProgress(
                total=sum(counts.values()),
                ranked=counts.get(ExecutionStatus.SUCCEEDED, 0),
                failed=counts.get(ExecutionStatus.FAILED, 0),
                reviewed=confirmed + not_found,
                confirmed=confirmed,
                not_found=not_found,
            ),
            recall_ceiling=coverage.recall_ceiling,
        )

    async def list(
        self, *, qa_set_id: uuid.UUID | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[list[TransferView], int]:
        """One page of jobs, newest first, with their progress."""
        jobs = await self.jobs.list(qa_set_id=qa_set_id, limit=limit, offset=offset)
        return (
            [await self.view(job) for job in jobs],
            await self.jobs.count(qa_set_id=qa_set_id),
        )

    async def cancel(self, transfer_job_id: uuid.UUID) -> TransferView:
        """Stop the ranking of a job; the candidates already written stay reviewable.

        Raises:
            TransferJobNotFoundError: If the job does not exist.
            TransferNotCancellableError: If the job already ended.
        """
        job = await self.get(transfer_job_id)
        if job.status not in (TransferStatus.PENDING, TransferStatus.RUNNING):
            raise TransferNotCancellableError(job.id, job.status.value)
        if self.workflows is not None and job.workflow_id is not None:
            await self.workflows.cancel(job.workflow_id)
        job.status = TransferStatus.CANCELLED
        await self.session.flush()
        return await self.view(job)

    async def resume(self, transfer_job_id: uuid.UUID) -> TransferView:
        """Relaunch a job, ranking only the questions that were not ranked yet.

        Raises:
            TransferJobNotFoundError: If the job does not exist.
            TransferNotResumableError: If it is running or every question is ranked.
        """
        job = await self.get(transfer_job_id)
        if job.status == TransferStatus.RUNNING:
            raise TransferNotResumableError(job.id, "it is still running")
        counts = await self.job_questions.count_by_status(job.id)
        if counts.get(ExecutionStatus.SUCCEEDED, 0) == sum(counts.values()):
            raise TransferNotResumableError(job.id, "every question is ranked")
        job.status = TransferStatus.PENDING
        job.error = None
        await self.session.flush()
        await self._launch(job)
        return await self.view(job)

    async def queue(
        self,
        transfer_job_id: uuid.UUID,
        *,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[QueueRow], int]:
        """The questions of a job with where each stands, optionally of one state.

        Without a state the questions waiting for a person come first (pre-selected, then
        with plausible candidates, then without), so working down the list is the fastest
        way through the review; the others follow.
        """
        rows = await self._queue_rows(await self.get(transfer_job_id))
        if state is not None:
            rows = [row for row in rows if row.state == state]
        else:
            order = {name: index for index, name in enumerate(QUEUE_STATES)}
            rows = sorted(rows, key=lambda row: order[row.state])
        return rows[offset : offset + limit], len(rows)

    async def review(
        self, transfer_job_id: uuid.UUID, question_id: uuid.UUID
    ) -> QuestionReview:
        """A question opened for review: its candidates best first and what they match.

        With a source, the chunks confirmed there are returned as the reference, so the
        reviewer reads what is being looked for. The next question waiting in the queue is
        named, for a review that goes from one question to the next.

        Raises:
            TransferJobNotFoundError: If the job does not exist.
            QuestionNotInTransferError: If the job does not include the question.
        """
        job = await self.get(transfer_job_id)
        if await self.job_questions.get(job.id, question_id) is None:
            raise QuestionNotInTransferError(job.id, question_id)
        rows = await self._queue_rows(job)
        row = next(item for item in rows if item.question_id == question_id)
        waiting = [
            item.question_id
            for item in sorted(
                (item for item in rows if item.state in UNDECIDED_STATES),
                key=lambda item: UNDECIDED_STATES.index(item.state),
            )
            if item.question_id != question_id
        ]
        question = (await self.questions.list_by_ids([question_id]))[0]
        reference = (
            await self.pool.confirmed_chunks(question_id, job.source_configuration_id)
            if job.source_configuration_id is not None
            else []
        )
        return QuestionReview(
            question=question,
            state=row.state,
            evidence_status=row.evidence_status,
            reference=reference,
            candidates=[
                ReviewCandidate(
                    candidate=candidate,
                    chunk_text=chunk.text,
                    ordinal=chunk.ordinal,
                    page=_page(chunk),
                    document_id=document_id,
                    filename=filename,
                )
                for candidate, chunk, document_id, filename in (
                    await self.candidates.for_question(job.id, question_id)
                )
            ],
            next_question_id=waiting[0] if waiting else None,
        )

    async def _queue_rows(self, job: TransferJob) -> list[QueueRow]:
        rows = await self.job_questions.list_with_questions(job.id)
        statuses = await self.evidence.statuses(
            [question.id for _, question in rows], job.target_configuration_id
        )
        summaries = await self.candidates.summaries(job.id)
        result = []
        for ranking, question in rows:
            status = statuses.get(question.id)
            evidence = status.value if status is not None else NOT_REVIEWED
            summary = summaries.get(question.id)
            result.append(
                QueueRow(
                    question_id=question.id,
                    text=question.text,
                    state=queue_state(ranking.status, evidence, summary),
                    evidence_status=evidence,
                    top_score=summary.top_score if summary else None,
                    plausible=summary.plausible if summary else 0,
                    preselected=summary.preselected if summary else 0,
                    error=ranking.error,
                )
            )
        return result

    async def _uncovered(
        self, question_ids: list[uuid.UUID], configuration_id: uuid.UUID
    ) -> list[UncoveredQuestion]:
        gold = await self.questions.gold_by_question(question_ids)
        materialised = await self.pool.materialised_documents(
            configuration_id,
            sorted({document_id for docs in gold.values() for document_id, _ in docs}),
        )
        texts = {
            question.id: question.text
            for question in await self.questions.list_by_ids(question_ids)
        }
        uncovered = []
        for question_id in question_ids:
            documents = gold.get(question_id, [])
            missing = [item for item in documents if item[0] not in materialised]
            if not documents:
                uncovered.append(
                    UncoveredQuestion(
                        question_id, texts[question_id], NO_GOLD_DOCUMENTS, []
                    )
                )
            elif missing:
                uncovered.append(
                    UncoveredQuestion(
                        question_id,
                        texts[question_id],
                        DOCUMENTS_NOT_MATERIALISED,
                        missing,
                    )
                )
        return uncovered

    async def _launch(self, job: TransferJob) -> None:
        if self.workflows is None:
            return
        await self.workflows.start(
            TRANSFER_DATASET_WORKFLOW,
            arg={
                "transfer_job_id": str(job.id),
                "concurrency": job.progress.get(
                    "concurrency", DEFAULT_TRANSFER_CONCURRENCY
                ),
            },
            workflow_id=job.workflow_id or transfer_dataset_workflow_id(job.id),
            task_queue=EXPERIMENTS_TASK_QUEUE,
        )
