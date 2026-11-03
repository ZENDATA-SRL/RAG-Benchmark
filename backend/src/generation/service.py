from __future__ import annotations

import dataclasses
import datetime as dt
import math
import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.generation.constants import (
    CROSS_BATCH,
    DEFAULT_CONCURRENCY,
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_TOKENS,
    GENERATED_TAG,
)
from src.generation.exceptions import (
    ChunksOutsideJobError,
    CrossNeedsDocumentsError,
    DocumentsOutsideCorpusError,
    GenerationJobNotFoundError,
    GenerationNotCancellableError,
    GenerationNotResumableError,
    NothingToGenerateError,
    ProposalAlreadyReviewedError,
    ProposalNotFoundError,
    QASetWithoutCorpusError,
    UnmaterializedDocumentsChoiceRequiredError,
)
from src.generation.models import GeneratedQuestion, GenerationJob, GenerationUnit
from src.generation.prompts import PROMPT_VERSION
from src.generation.repository import (
    CorpusDocumentState,
    CorpusTextRepository,
    GenerationJobRepository,
    GenerationUnitRepository,
    ProposalChunkRow,
    ProposalRepository,
)
from src.generation.verification import DEFAULT_LIMITS
from src.infrastructure.database.enums import (
    EvidenceLinkStatus,
    ExecutionStatus,
    GeneratedKind,
    GenerationPhase,
    GenerationStatus,
    ProposalStatus,
    RelevanceGrade,
)
from src.infrastructure.observability import trace_url
from src.infrastructure.temporal import WorkflowClient
from src.infrastructure.temporal.workflow_ids import (
    EXPERIMENTS_TASK_QUEUE,
    GENERATE_QUESTIONS_WORKFLOW,
    generate_questions_workflow_id,
)
from src.pipelines.service import ChunkingConfigurationService
from src.qa_sets.evidence import EvidenceChunkInput, EvidenceService
from src.qa_sets.exceptions import InvalidEvidenceError
from src.qa_sets.service import AnswerRef, QASetService, QuestionDraft, QuestionService
from src.settings import get_settings


@dataclasses.dataclass(frozen=True)
class Estimate:
    """The most a job can cost: every unit using all of its steps."""

    documents: int
    document_units: int
    cross_units: int
    max_steps: int
    max_model_calls: int
    target_questions: int


@dataclasses.dataclass(frozen=True)
class Plan:
    """What a job would read and run, before it exists."""

    document_ids: list[uuid.UUID]
    excluded: list[tuple[uuid.UUID, str]]
    estimate: Estimate
    corpus: list[CorpusDocumentState] = dataclasses.field(default_factory=list)
    left_out: set[uuid.UUID] = dataclasses.field(default_factory=set)


@dataclasses.dataclass(frozen=True)
class PhaseProgress:
    units: int
    succeeded: int
    failed: int
    running: int
    target: int
    produced: int


@dataclasses.dataclass(frozen=True)
class ProposalCounts:
    pending: int
    accepted: int
    rejected: int
    by_kind: dict[str, int]


@dataclasses.dataclass(frozen=True)
class GenerationProgress:
    """How far the units and the review of a job have gone."""

    document: PhaseProgress
    cross: PhaseProgress
    discards: dict[str, int]
    proposals: ProposalCounts
    documents_covered: int
    combinations: int


@dataclasses.dataclass(frozen=True)
class GenerationView:
    """A job with its progress, read live from its units and proposals."""

    job: GenerationJob
    progress: GenerationProgress
    estimate: Estimate
    excluded: list[tuple[uuid.UUID, str]] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class UnitView:
    unit: GenerationUnit
    filename: str | None
    trace_url: str | None


@dataclasses.dataclass(frozen=True)
class ProposalView:
    """A proposal with the chunks it cites."""

    proposal: GeneratedQuestion
    chunks: list[ProposalChunkRow]


@dataclasses.dataclass(frozen=True)
class ProposalReview:
    """A proposal opened for review, with where it comes from and what follows."""

    view: ProposalView
    job: GenerationJob
    phase: GenerationPhase
    trace_url: str | None
    next_proposal_id: uuid.UUID | None


@dataclasses.dataclass(frozen=True)
class Decision:
    view: ProposalView
    question_id: uuid.UUID | None
    next_proposal_id: uuid.UUID | None


def estimate(
    documents: int, *, per_document: int, cross_document: int, max_steps: int
) -> Estimate:
    """Units and model calls a job takes at most, from what it is asked."""
    document_units = documents if per_document > 0 else 0
    cross_units = math.ceil(cross_document / CROSS_BATCH)
    return Estimate(
        documents=documents,
        document_units=document_units,
        cross_units=cross_units,
        max_steps=max_steps,
        max_model_calls=(document_units + cross_units) * max_steps,
        target_questions=document_units * per_document + cross_document,
    )


def kind_of(chunk_documents: Sequence[uuid.UUID]) -> GeneratedKind:
    """The kind of a question from the documents of its chunks, one entry per chunk."""
    if len(set(chunk_documents)) > 1:
        return GeneratedKind.CROSS
    if len(chunk_documents) > 1:
        return GeneratedKind.MULTI
    return GeneratedKind.SINGLE


def tags_for(kind: GeneratedKind) -> list[str]:
    """The tags of an accepted question, which the slicing by tag reads."""
    return [GENERATED_TAG, f"{GENERATED_TAG}:{kind.value}"]


def _unit_trace_url(unit: GenerationUnit | None) -> str | None:
    if unit is None:
        return None
    return trace_url(unit.langfuse_trace_id, get_settings().langfuse_host)


class GenerationService:
    """Creation of generation jobs, their progress, their units, cancel and resume."""

    def __init__(
        self, session: AsyncSession, workflows: WorkflowClient | None = None
    ) -> None:
        self.session = session
        self.workflows = workflows
        self.jobs = GenerationJobRepository(session)
        self.units = GenerationUnitRepository(session)
        self.proposals = ProposalRepository(session)
        self.texts = CorpusTextRepository(session)
        self.qa_sets = QASetService(session)

    async def plan(
        self,
        *,
        qa_set_id: uuid.UUID,
        chunking_configuration_id: uuid.UUID,
        per_document: int,
        cross_document: int,
        document_ids: Sequence[uuid.UUID] | None = None,
        excluded_document_ids: Sequence[uuid.UUID] = (),
        exclude_unmaterialized: bool = False,
        max_steps: int | None = None,
    ) -> Plan:
        """Check what a job is asked and say what it would read and cost.

        The documents are those of the set's origin corpus, or only the chosen ones, without
        the excluded ones: questions can be asked of a few documents without unticking
        the rest of the corpus. A document without ready chunks or parsed text in the configuration cannot be read,
        so the caller must exclude those explicitly: otherwise the corpus would look
        covered when part of it was never read.

        Raises:
            QASetNotFoundError: If the set does not exist.
            QASetWithoutCorpusError: If the set has no origin corpus.
            ChunkingConfigurationNotFoundError: If the configuration does not exist.
            NothingToGenerateError: If no question is asked or no document is left.
            UnmaterializedDocumentsChoiceRequiredError: If some documents cannot be read
                and were not excluded.
            DocumentsOutsideCorpusError: If a chosen document is not in the corpus.
            CrossNeedsDocumentsError: If cross questions are asked of a single document.
        """
        qa_set = await self.qa_sets.get(qa_set_id)
        if qa_set.origin_corpus_id is None:
            raise QASetWithoutCorpusError(qa_set_id)
        await ChunkingConfigurationService(self.session).get(chunking_configuration_id)
        if per_document <= 0 and cross_document <= 0:
            raise NothingToGenerateError("ask for at least one question")

        excluded = set(excluded_document_ids)
        corpus = await self.texts.corpus_documents(
            qa_set.origin_corpus_id, chunking_configuration_id
        )
        if document_ids is not None:
            chosen = set(document_ids)
            known = {state.document_id for state in corpus}
            outside = [item for item in document_ids if item not in known]
            if outside:
                raise DocumentsOutsideCorpusError(outside)
            excluded |= known - chosen
        states = [state for state in corpus if state.document_id not in excluded]
        unreadable = [
            (state.document_id, state.filename)
            for state in states
            if not state.materialised
        ]
        if unreadable and not exclude_unmaterialized:
            raise UnmaterializedDocumentsChoiceRequiredError(
                [
                    {"document_id": str(document_id), "filename": filename}
                    for document_id, filename in unreadable
                ]
            )
        readable = [state.document_id for state in states if state.materialised]
        if not readable:
            raise NothingToGenerateError("no document of the corpus can be read")
        if cross_document > 0 and len(readable) < 2:
            raise CrossNeedsDocumentsError(len(readable))
        return Plan(
            document_ids=readable,
            excluded=unreadable,
            estimate=estimate(
                len(readable),
                per_document=per_document,
                cross_document=cross_document,
                max_steps=max_steps or DEFAULT_MAX_STEPS,
            ),
            corpus=corpus,
            left_out=excluded,
        )

    async def create(
        self,
        *,
        qa_set_id: uuid.UUID,
        chunking_configuration_id: uuid.UUID,
        per_document: int,
        cross_document: int,
        provider: str,
        model: str,
        temperature: float,
        region: str | None = None,
        language: str | None = None,
        instructions: str | None = None,
        max_steps: int | None = None,
        document_ids: Sequence[uuid.UUID] | None = None,
        excluded_document_ids: Sequence[uuid.UUID] = (),
        exclude_unmaterialized: bool = False,
        concurrency: int | None = None,
    ) -> GenerationView:
        """Create a job with its units and start it on the worker.

        One unit per document for the questions of that document, then the questions
        across documents in units of a few, which the worker runs after the first phase
        and one after the other. The generator's parameters, the limits of the checks and
        the prompt version are saved on the job.

        Raises:
            The errors of `plan`.
        """
        plan = await self.plan(
            qa_set_id=qa_set_id,
            chunking_configuration_id=chunking_configuration_id,
            per_document=per_document,
            cross_document=cross_document,
            document_ids=document_ids,
            excluded_document_ids=excluded_document_ids,
            exclude_unmaterialized=exclude_unmaterialized,
            max_steps=max_steps,
        )
        job = self.jobs.add(
            GenerationJob(
                qa_set_id=qa_set_id,
                chunking_configuration_id=chunking_configuration_id,
                document_ids=plan.document_ids,
                params={
                    "per_document": per_document,
                    "cross_document": cross_document,
                    "provider": provider,
                    "model": model,
                    "region": region,
                    "temperature": temperature,
                    "max_tokens": DEFAULT_MAX_TOKENS,
                    "language": language or None,
                    "instructions": (instructions or "").strip() or None,
                    "max_steps": plan.estimate.max_steps,
                    "limits": dict(DEFAULT_LIMITS),
                },
                prompt_version=PROMPT_VERSION,
                progress={
                    "excluded": len(plan.excluded),
                    "concurrency": concurrency or DEFAULT_CONCURRENCY,
                },
            )
        )
        await self.session.flush()
        job.workflow_id = generate_questions_workflow_id(job.id)
        units: list[GenerationUnit] = []
        if per_document > 0:
            units += [
                GenerationUnit(
                    generation_job_id=job.id,
                    phase=GenerationPhase.DOCUMENT,
                    document_id=document_id,
                    position=position,
                    target=per_document,
                )
                for position, document_id in enumerate(plan.document_ids)
            ]
        for position in range(plan.estimate.cross_units):
            units.append(
                GenerationUnit(
                    generation_job_id=job.id,
                    phase=GenerationPhase.CROSS,
                    position=position,
                    target=min(CROSS_BATCH, cross_document - position * CROSS_BATCH),
                )
            )
        self.units.add_all(units)
        await self.session.flush()
        await self._launch(job)
        await self.session.refresh(job)
        return dataclasses.replace(await self.view(job), excluded=plan.excluded)

    async def get(self, generation_job_id: uuid.UUID) -> GenerationJob:
        """Return a job.

        Raises:
            GenerationJobNotFoundError: If it does not exist.
        """
        job = await self.jobs.get_by_id(generation_job_id)
        if job is None:
            raise GenerationJobNotFoundError(generation_job_id)
        return job

    async def view(self, job: GenerationJob) -> GenerationView:
        """A job with its progress read live, so a decision in the review shows at once."""
        units = await self.units.list_by_job(job.id)
        discards: dict[str, int] = {}
        for unit in units:
            for reason, count in (unit.discards or {}).items():
                discards[reason] = discards.get(reason, 0) + count
        counts = await self.proposals.counts(job.id)
        by_status = {status: 0 for status in ProposalStatus}
        by_kind = {kind.value: 0 for kind in GeneratedKind}
        for (status, kind), count in counts.items():
            by_status[status] += count
            if status != ProposalStatus.REJECTED:
                by_kind[kind.value] += count
        documents = await self.proposals.documents_by_proposal(job.id)
        covered = set().union(*documents.values()) if documents else set()
        combinations = {frozenset(docs) for docs in documents.values() if len(docs) > 1}
        params = job.params
        return GenerationView(
            job=job,
            progress=GenerationProgress(
                document=_phase(units, GenerationPhase.DOCUMENT),
                cross=_phase(units, GenerationPhase.CROSS),
                discards=discards,
                proposals=ProposalCounts(
                    pending=by_status[ProposalStatus.PENDING],
                    accepted=by_status[ProposalStatus.ACCEPTED],
                    rejected=by_status[ProposalStatus.REJECTED],
                    by_kind=by_kind,
                ),
                documents_covered=len(covered),
                combinations=len(combinations),
            ),
            estimate=estimate(
                len(job.document_ids),
                per_document=int(params.get("per_document", 0)),
                cross_document=int(params.get("cross_document", 0)),
                max_steps=int(params.get("max_steps", DEFAULT_MAX_STEPS)),
            ),
        )

    async def list(
        self, *, qa_set_id: uuid.UUID | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[list[GenerationView], int]:
        """One page of jobs, newest first, with their progress."""
        jobs = await self.jobs.list(qa_set_id=qa_set_id, limit=limit, offset=offset)
        return (
            [await self.view(job) for job in jobs],
            await self.jobs.count(qa_set_id=qa_set_id),
        )

    async def units_of(self, generation_job_id: uuid.UUID) -> list[UnitView]:
        """The units of a job, the document phase first, with their trace.

        Raises:
            GenerationJobNotFoundError: If the job does not exist.
        """
        job = await self.get(generation_job_id)
        units = await self.units.list_by_job(job.id)
        catalogue = await self.texts.catalogue(
            job.chunking_configuration_id,
            [unit.document_id for unit in units if unit.document_id is not None],
        )
        return [
            UnitView(
                unit=unit,
                filename=catalogue[unit.document_id].filename
                if unit.document_id in catalogue
                else None,
                trace_url=_unit_trace_url(unit),
            )
            for unit in units
        ]

    async def cancel(self, generation_job_id: uuid.UUID) -> GenerationView:
        """Stop a job; the questions already proposed stay reviewable.

        Raises:
            GenerationJobNotFoundError: If the job does not exist.
            GenerationNotCancellableError: If the job already ended.
        """
        job = await self.get(generation_job_id)
        if job.status not in (GenerationStatus.PENDING, GenerationStatus.RUNNING):
            raise GenerationNotCancellableError(job.id, job.status.value)
        if self.workflows is not None and job.workflow_id is not None:
            await self.workflows.cancel(job.workflow_id)
        job.status = GenerationStatus.CANCELLED
        await self.session.flush()
        return await self.view(job)

    async def resume(self, generation_job_id: uuid.UUID) -> GenerationView:
        """Relaunch a job, running only the units that did not succeed.

        Raises:
            GenerationJobNotFoundError: If the job does not exist.
            GenerationNotResumableError: If it is running or every unit succeeded.
        """
        job = await self.get(generation_job_id)
        if job.status == GenerationStatus.RUNNING:
            raise GenerationNotResumableError(job.id, "it is still running")
        units = await self.units.list_by_job(job.id)
        if all(unit.status == ExecutionStatus.SUCCEEDED for unit in units):
            raise GenerationNotResumableError(job.id, "every unit is done")
        job.status = GenerationStatus.PENDING
        job.error = None
        await self.session.flush()
        await self._launch(job)
        return await self.view(job)

    async def _launch(self, job: GenerationJob) -> None:
        if self.workflows is None:
            return
        await self.workflows.start(
            GENERATE_QUESTIONS_WORKFLOW,
            arg={
                "generation_job_id": str(job.id),
                "concurrency": job.progress.get("concurrency", DEFAULT_CONCURRENCY),
            },
            workflow_id=job.workflow_id or generate_questions_workflow_id(job.id),
            task_queue=EXPERIMENTS_TASK_QUEUE,
        )


def _phase(units: Sequence[GenerationUnit], phase: GenerationPhase) -> PhaseProgress:
    selected = [unit for unit in units if unit.phase is phase]
    return PhaseProgress(
        units=len(selected),
        succeeded=sum(1 for u in selected if u.status == ExecutionStatus.SUCCEEDED),
        failed=sum(1 for u in selected if u.status == ExecutionStatus.FAILED),
        running=sum(1 for u in selected if u.status == ExecutionStatus.RUNNING),
        target=sum(u.target for u in selected),
        produced=sum(u.produced for u in selected),
    )


class ReviewService:
    """The review queue of a job: nothing generated is gold until a person accepts it."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.jobs = GenerationService(session)
        self.units = GenerationUnitRepository(session)
        self.proposals = ProposalRepository(session)
        self.texts = CorpusTextRepository(session)

    async def list(
        self,
        generation_job_id: uuid.UUID,
        *,
        status: ProposalStatus | None = None,
        kind: GeneratedKind | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ProposalView], int]:
        """One page of the proposals of a job, in the order they were saved.

        Raises:
            GenerationJobNotFoundError: If the job does not exist.
        """
        job = await self.jobs.get(generation_job_id)
        rows, total = await self.proposals.list(
            job.id, status=status, kind=kind, limit=limit, offset=offset
        )
        chunks = await self.proposals.chunks_of([row.id for row in rows])
        return [ProposalView(row, chunks.get(row.id, [])) for row in rows], total

    async def review(
        self, proposal_id: uuid.UUID, *, kind: GeneratedKind | None = None
    ) -> ProposalReview:
        """A proposal opened for review, with its chunks and the next one waiting.

        Raises:
            ProposalNotFoundError: If it does not exist.
        """
        proposal = await self._get(proposal_id)
        job = await self.jobs.get(proposal.generation_job_id)
        unit = await self.units.get_by_id(proposal.unit_id)
        return ProposalReview(
            view=await self._view(proposal),
            job=job,
            phase=unit.phase,
            trace_url=_unit_trace_url(unit),
            next_proposal_id=await self.proposals.next_pending(
                job.id, after=proposal, kind=kind
            ),
        )

    async def accept(
        self,
        proposal_id: uuid.UUID,
        *,
        text: str,
        answer: str,
        chunks: Sequence[tuple[uuid.UUID, RelevanceGrade]],
        annotator: str,
    ) -> Decision:
        """Turn a proposal into a question of the set, with confirmed evidence.

        In one transaction: the question with its expected answer and the tags of its
        kind, then its evidence through the same path as manual authoring, which checks
        the chunks and derives the gold documents. The text, the answer and the chunks
        may be corrected by the reviewer; the proposal keeps what the agent wrote. The
        kind is read again from the chunks accepted.

        Raises:
            ProposalNotFoundError: If it does not exist.
            ProposalAlreadyReviewedError: If it was already decided.
            InvalidEvidenceError: If no annotator is named.
            ChunksOutsideJobError: If a chunk is not one of the job's documents.
            DuplicateQuestionError: If the set already has a question with this text.
        """
        proposal = await self._locked(proposal_id)
        job = await self.jobs.get(proposal.generation_job_id)
        if not annotator.strip():
            raise InvalidEvidenceError(
                "annotator_required", "accepting a question needs the annotator's name"
            )
        chunk_ids = list(dict.fromkeys(chunk_id for chunk_id, _ in chunks))
        rows = await self.texts.chunks_by_id(job.chunking_configuration_id, chunk_ids)
        documents = set(job.document_ids)
        outside = [
            chunk_id
            for chunk_id in chunk_ids
            if chunk_id not in rows or rows[chunk_id].document_id not in documents
        ]
        if outside:
            raise ChunksOutsideJobError(outside)

        grades = dict(chunks)
        kind = kind_of([rows[chunk_id].document_id for chunk_id in chunk_ids])
        question = await QuestionService(self.session).create(
            job.qa_set_id,
            QuestionDraft(
                text=text.strip(),
                tags=tags_for(kind),
                answerable=True,
                expected_answers=[AnswerRef(text=answer.strip(), is_primary=True)],
                gold_document_ids=[],
            ),
        )
        await EvidenceService(self.session).put(
            question.id,
            job.chunking_configuration_id,
            status=EvidenceLinkStatus.CONFIRMED,
            chunks=[
                EvidenceChunkInput(chunk_id=chunk_id, relevance=grades[chunk_id])
                for chunk_id in chunk_ids
            ],
            annotator=annotator,
        )
        proposal.status = ProposalStatus.ACCEPTED
        proposal.accepted_question_id = question.id
        self._reviewed(proposal, annotator)
        await self.session.flush()
        return Decision(
            view=await self._view(proposal),
            question_id=question.id,
            next_proposal_id=await self.proposals.next_pending(job.id, after=proposal),
        )

    async def reject(
        self, proposal_id: uuid.UUID, *, annotator: str | None = None
    ) -> Decision:
        """Reject a proposal: it leaves no trace in the set.

        Raises:
            ProposalNotFoundError: If it does not exist.
            ProposalAlreadyReviewedError: If it was already decided.
        """
        proposal = await self._locked(proposal_id)
        proposal.status = ProposalStatus.REJECTED
        self._reviewed(proposal, annotator)
        await self.session.flush()
        return Decision(
            view=await self._view(proposal),
            question_id=None,
            next_proposal_id=await self.proposals.next_pending(
                proposal.generation_job_id, after=proposal
            ),
        )

    async def _get(self, proposal_id: uuid.UUID) -> GeneratedQuestion:
        proposal = await self.proposals.get_by_id(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(proposal_id)
        return proposal

    async def _locked(self, proposal_id: uuid.UUID) -> GeneratedQuestion:
        proposal = await self.proposals.get_for_update(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(proposal_id)
        if proposal.status != ProposalStatus.PENDING:
            raise ProposalAlreadyReviewedError(proposal.id, proposal.status.value)
        return proposal

    async def _view(self, proposal: GeneratedQuestion) -> ProposalView:
        chunks = await self.proposals.chunks_of([proposal.id])
        return ProposalView(proposal, chunks.get(proposal.id, []))

    @staticmethod
    def _reviewed(proposal: GeneratedQuestion, annotator: str | None) -> None:
        proposal.reviewed_by = (annotator or "").strip() or None
        proposal.reviewed_at = dt.datetime.now(dt.UTC)
