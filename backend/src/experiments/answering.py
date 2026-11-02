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
from src.infrastructure.database.enums import ExecutionStatus
from src.qa_sets.models import Question
from src.retrieval.exceptions import RetrievalBackendError
from src.retrieval.service import RetrievalService


class AnswerRunner:
    """Run one execution of a Q&A experiment: answer the question, record it, score it.

    The answer system is given the same `RetrievalService.search` the retrieval endpoint
    exposes, bound to the variant and the execution, so every search it makes is recorded
    as a call of the execution exactly as in a retrieval experiment.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.executions = ExecutionRepository(session)
        self.evaluation = EvaluationService(session)

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
        await self.session.flush()

        try:
            if variant.answer_profile_id is None:
                raise DomainError("the variant has no answer profile")
            profile = await self.session.get(AnswerProfile, variant.answer_profile_id)
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
                index_build_id=variant.index_build_id,
                retrieval_profile_id=variant.retrieval_profile_id,
                execution_id=execution.id,
            )
            result = await system.answer(question.text, dict(profile.params), retrieve)
        except (RetrievalBackendError, AnswerProviderError):
            raise
        except DomainError as error:
            return await ExecutionRunner(self.session).fail(execution.id, error.message)

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
    query: str,
    *,
    index_build_id: uuid.UUID,
    retrieval_profile_id: uuid.UUID,
    execution_id: uuid.UUID,
):
    return await service.search(
        index_build_id=index_build_id,
        retrieval_profile_id=retrieval_profile_id,
        query=query,
        execution_id=execution_id,
    )
