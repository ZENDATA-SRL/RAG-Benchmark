from __future__ import annotations

import functools
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.answer_profiles.models import AnswerProfile
from src.answering.exceptions import AnswerProviderError
from src.answering.registry import resolve_answer_system
from src.components.models import Component, ComponentVersion
from src.core.exceptions import DomainError
from src.experiments.evaluation import (
    EvaluationService,
    ExecutionOutcome,
    ExecutionRunner,
    clear_answer,
)
from src.experiments.exceptions import ExecutionNotFoundError
from src.experiments.repository import ExecutionRepository, ExperimentRepository
from src.experiments.tracing import TRACE_NAME, ExperimentTracing
from src.infrastructure.database.enums import ExecutionStatus
from src.infrastructure.observability import Tracer, get_tracer
from src.qa_sets.models import Question
from src.retrieval.exceptions import RetrievalBackendError
from src.retrieval.service import RetrievalResult, RetrievalService

# Characters of each retrieved chunk shown in its span: enough to recognise the passage,
# while the full text stays in the database.
_EXCERPT_CHARS = 300


class AnswerRunner:
    """Run one execution of a Q&A experiment: answer the question, record it, score it.

    The answer system is given the same `RetrievalService.search` the retrieval endpoint
    exposes, bound to the variant and the execution, so every search it makes is recorded
    as a call of the execution exactly as in a retrieval experiment.

    Each attempt is traced under a trace id derived from the execution, with one span per
    search and whatever the answer system records itself, such as the call to the model.
    """

    def __init__(self, session: AsyncSession, tracer: Tracer | None = None) -> None:
        self.session = session
        self.executions = ExecutionRepository(session)
        self.evaluation = EvaluationService(session)
        self.tracer = tracer or get_tracer()
        self.tracing = ExperimentTracing(session, self.tracer)

    async def run(self, execution_id: uuid.UUID) -> ExecutionOutcome:
        """Answer the question of an execution and score it.

        An execution that already succeeded is returned as it is, and what an earlier,
        interrupted attempt recorded is discarded before answering again.

        A failure of the embedder, the vector store or the model provider is raised, so
        the workflow retries it with backoff. Any other domain error, such as an answer
        not in the expected shape or a provider without credentials, is permanent for
        this question: the execution is marked `failed` with the reason and the run goes
        on.

        Raises:
            ExecutionNotFoundError: If the execution does not exist.
            RetrievalBackendError: If the embedder or the vector store failed.
            AnswerProviderError: If the model provider failed.
        """
        execution = await self.executions.get_by_id(execution_id)
        if execution is None:
            raise ExecutionNotFoundError(execution_id)
        if execution.status == ExecutionStatus.SUCCEEDED:
            return ExecutionOutcome(execution.id, ExecutionStatus.SUCCEEDED)

        question = await self.session.get(Question, execution.question_id)
        variant = await ExperimentRepository(self.session).get_variant(
            execution.variant_id
        )
        execution.status = ExecutionStatus.RUNNING
        await self.executions.clear_calls(execution.id)
        clear_answer(execution)
        trace = await self.tracing.for_execution(execution, question)
        execution.langfuse_trace_id = trace.trace_id
        await self.session.flush()

        with (
            self.tracer.observe(
                TRACE_NAME,
                trace_id=trace.trace_id,
                input={"question": question.text},
            ) as root,
            self.tracer.attributes(
                metadata=trace.metadata, tags=trace.tags, trace_name=TRACE_NAME
            ),
            self.tracing.experiment(trace, root),
        ):
            try:
                if variant.answer_profile_id is None:
                    raise DomainError("the variant has no answer profile")
                profile = await self.session.get(
                    AnswerProfile, variant.answer_profile_id
                )
                version = await self.session.get(
                    ComponentVersion, profile.component_version_id
                )
                component = await self.session.get(Component, version.component_id)
                try:
                    system = resolve_answer_system(component.key)
                except KeyError:
                    raise DomainError(
                        f"answer system {component.key!r} has no implementation"
                    ) from None
                retrieve = functools.partial(
                    _search,
                    RetrievalService(self.session),
                    self.tracer,
                    index_build_id=variant.index_build_id,
                    retrieval_profile_id=variant.retrieval_profile_id,
                    execution_id=execution.id,
                )
                result = await system.answer(
                    question.text, dict(profile.params), retrieve, self.tracer
                )
            except (RetrievalBackendError, AnswerProviderError):
                raise
            except DomainError as error:
                root.update(level="ERROR", status_message=error.message)
                return await ExecutionRunner(self.session).fail(
                    execution.id, error.message
                )
            root.update(
                output={
                    "answer": result.answer,
                    "refused": result.refused,
                    "cited_chunk_ids": [str(chunk) for chunk in result.citations],
                }
            )

        execution.answer_text = result.answer
        execution.refused = result.refused
        execution.usage = result.usage
        execution.timings = result.timings
        execution.cited_chunk_ids = list(dict.fromkeys(result.citations))
        execution.status = ExecutionStatus.SUCCEEDED
        execution.error = None
        await self.session.flush()
        await self.evaluation.evaluate_execution(execution.id)
        return ExecutionOutcome(execution.id, ExecutionStatus.SUCCEEDED)


async def _search(
    service: RetrievalService,
    tracer: Tracer,
    query: str,
    *,
    index_build_id: uuid.UUID,
    retrieval_profile_id: uuid.UUID,
    execution_id: uuid.UUID,
) -> RetrievalResult:
    with tracer.observe(
        "retrieval", as_type="retriever", input={"query": query}
    ) as span:
        result = await service.search(
            index_build_id=index_build_id,
            retrieval_profile_id=retrieval_profile_id,
            query=query,
            execution_id=execution_id,
        )
        span.update(
            output=[
                {
                    "rank": hit.rank,
                    "score": hit.score,
                    "chunk_id": str(hit.chunk_id) if hit.chunk_id else None,
                    "document_id": str(hit.document_id) if hit.document_id else None,
                    "filename": hit.filename,
                    "page": hit.page,
                    "text": (hit.text or "")[:_EXCERPT_CHARS],
                }
                for hit in result.hits
            ],
            metadata={
                "index_build_id": str(index_build_id),
                "retrieval_profile_id": str(retrieval_profile_id),
                "hits": len(result.hits),
                "embed_ms": result.timings.embed_ms,
                "search_ms": result.timings.search_ms,
                "total_ms": result.timings.total_ms,
            },
        )
    return result
