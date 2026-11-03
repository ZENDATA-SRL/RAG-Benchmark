from __future__ import annotations

import dataclasses
import logging
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.answering.chat_models import (
    is_output_error,
    missing_credentials,
    resolve_chat_model,
)
from src.generation.agent import MAX_STEPS, run_agent
from src.generation.constants import (
    AGENT_FINISHED,
    AGENT_STOPPED,
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    INVALID_OUTPUT,
    MAX_STEPS_REACHED,
    TARGET_REACHED,
    TRACE_NAME,
)
from src.generation.exceptions import (
    GenerationJobNotFoundError,
    GenerationProviderError,
    GenerationUnitNotFoundError,
)
from src.generation.models import GenerationJob, GenerationUnit
from src.generation.prompts import (
    PromptOptions,
    cross_task,
    document_task,
    system_prompt,
)
from src.generation.refs import Refs
from src.generation.repository import (
    CorpusTextRepository,
    GenerationJobRepository,
    GenerationUnitRepository,
    ProposalRepository,
)
from src.generation.service import GenerationService
from src.generation.tools import GenerationTools, UnitScope
from src.generation.verification import DEFAULT_LIMITS
from src.generation.zones import zones
from src.infrastructure.database.enums import (
    ExecutionStatus,
    GenerationPhase,
    GenerationStatus,
)
from src.infrastructure.observability import Tracer, get_tracer
from src.qa_sets.repository import QuestionRepository

logger = logging.getLogger(__name__)

# Langfuse keeps trace-level metadata as short strings.
_MAX_VALUE = 200


@dataclasses.dataclass(frozen=True)
class UnitRef:
    """A unit as the workflow pages through them: its id and its place in the phase."""

    unit_id: str
    position: int


def model_params(params: dict[str, Any]) -> dict[str, Any]:
    """The chat model parameters of a job, in the shape `resolve_chat_model` reads."""
    return {
        "provider": params["provider"],
        "model": params["model"],
        "temperature": params.get("temperature", DEFAULT_TEMPERATURE),
        "max_tokens": params.get("max_tokens", DEFAULT_MAX_TOKENS),
        "region": params.get("region"),
    }


class GenerationRunner:
    """Run the units of a generation job; what the worker calls.

    A unit is the unit of resume: one that succeeded is never run again, and one that was
    interrupted starts again with the questions it already saved in its context and only
    what is left of its target.
    """

    def __init__(
        self,
        session: AsyncSession,
        tracer: Tracer | None = None,
        chat_model: Callable[[dict[str, Any]], Any] = resolve_chat_model,
    ) -> None:
        self.session = session
        self.tracer = tracer or get_tracer()
        self.chat_model = chat_model
        self.jobs = GenerationJobRepository(session)
        self.units = GenerationUnitRepository(session)
        self.proposals = ProposalRepository(session)
        self.texts = CorpusTextRepository(session)
        self.questions = QuestionRepository(session)

    async def open_job(self, generation_job_id: uuid.UUID) -> bool:
        """Mark a job `running` for this attempt; whether there is anything to run.

        The model credentials are checked here, on the worker that holds them: without
        them the job fails at once with the reason, before any unit is attempted. A
        cancelled job is not reopened.
        """
        job = await self._job(generation_job_id)
        if job.status == GenerationStatus.CANCELLED:
            return False
        reason = missing_credentials(job.params["provider"])
        if reason is not None:
            job.status = GenerationStatus.FAILED
            job.error = f"missing_credentials: {job.params['provider']}: {reason}"
            await self.session.flush()
            return False
        job.status = GenerationStatus.RUNNING
        job.error = None
        await self.units.reset_running(job.id)
        await self.session.flush()
        return True

    async def unfinished_units(
        self,
        generation_job_id: uuid.UUID,
        phase: GenerationPhase,
        *,
        after_position: int | None,
        limit: int,
    ) -> list[UnitRef]:
        """One page of the units of a phase not done yet, in their order."""
        ids = await self.units.unfinished_ids(
            generation_job_id, phase, after_position=after_position, limit=limit
        )
        result = []
        for unit_id in ids:
            unit = await self.units.get_by_id(unit_id)
            result.append(UnitRef(str(unit.id), unit.position))
        return result

    async def run_unit(
        self, unit_id: uuid.UUID, on_step: Callable[[], None] = lambda: None
    ) -> ExecutionStatus:
        """Let the agent write the questions of one unit; returns the unit's status.

        Each question is saved, in its own transaction, as soon as it passes the checks.
        The unit then succeeds whatever the agent achieved: a target not reached shows as
        fewer questions produced than asked, with the reason the run ended. A failure of
        the provider is raised, so the workflow retries the unit, which restarts from what
        is left; an answer the model got wrong ends the unit with what it saved.

        Raises:
            GenerationUnitNotFoundError: If the unit does not exist.
            GenerationProviderError: If the model provider failed.
        """
        unit = await self.units.get_by_id(unit_id)
        if unit is None:
            raise GenerationUnitNotFoundError(unit_id)
        if unit.status == ExecutionStatus.SUCCEEDED:
            return unit.status
        job = await self._job(unit.generation_job_id)
        if job.status == GenerationStatus.CANCELLED:
            return unit.status
        params = job.params
        reason = missing_credentials(params["provider"])
        if reason is not None:
            await self.fail_unit(unit.id, f"missing_credentials: {reason}")
            return ExecutionStatus.FAILED

        unit.status = ExecutionStatus.RUNNING
        unit.error = None
        unit.produced = await self.proposals.count_by_unit(unit.id)
        trace_id = self.tracer.trace_id(str(unit.id))
        unit.langfuse_trace_id = trace_id
        await self.session.commit()

        scope, task = await self._prepare(job, unit, on_step)
        if scope.remaining == 0 and (
            unit.phase is GenerationPhase.CROSS or unit.summary is not None
        ):
            return await self._close(unit, TARGET_REACHED)

        options = PromptOptions(
            language=params.get("language"), instructions=params.get("instructions")
        )
        tools = GenerationTools(scope).tools()
        end = AGENT_STOPPED
        with (
            self.tracer.observe(
                TRACE_NAME,
                trace_id=trace_id,
                input={"task": task},
            ) as root,
            self.tracer.attributes(
                metadata=await self._metadata(job, unit),
                tags=["generation", f"phase:{unit.phase.value}"],
                trace_name=TRACE_NAME,
            ),
        ):
            try:
                outcome = await run_agent(
                    self.chat_model(model_params(params)),
                    tools,
                    system_prompt=system_prompt(options),
                    task=task,
                    max_steps=int(params.get("max_steps", DEFAULT_MAX_STEPS)),
                    # A retry of the unit repeats its prefix: same key, same cache.
                    cache_key=str(unit.id),
                    callbacks=self.tracer.langchain_callbacks(),
                )
            except SQLAlchemyError:
                raise
            except Exception as error:
                if not is_output_error(error):
                    raise GenerationProviderError(
                        params["provider"], str(error) or type(error).__name__
                    ) from error
                logger.warning("generation unit %s: output error", unit.id)
                root.update(level="WARNING", status_message=str(error))
                outcome = INVALID_OUTPUT
            if scope.remaining == 0:
                end = TARGET_REACHED
            elif outcome == INVALID_OUTPUT:
                end = INVALID_OUTPUT
            elif scope.finished:
                end = AGENT_FINISHED
            elif outcome == MAX_STEPS:
                end = MAX_STEPS_REACHED
            root.update(
                output={
                    "saved": scope.saved,
                    "produced": unit.produced,
                    "target": unit.target,
                    "end_reason": end,
                    "discards": unit.discards,
                }
            )
        return await self._close(unit, end)

    async def fail_unit(self, unit_id: uuid.UUID, error: str) -> ExecutionStatus:
        """Mark a unit `failed` with its reason; the job goes on with the others."""
        unit = await self.units.get_by_id(unit_id)
        if unit is None:
            raise GenerationUnitNotFoundError(unit_id)
        unit.status = ExecutionStatus.FAILED
        unit.error = error
        await self.session.flush()
        return unit.status

    async def record_progress(self, generation_job_id: uuid.UUID) -> None:
        """Copy the counters of the units and the proposals onto the job row."""
        job = await self._job(generation_job_id)
        view = await GenerationService(self.session).view(job)
        job.progress = {**job.progress, "snapshot": dataclasses.asdict(view.progress)}
        await self.session.flush()

    async def finish_job(self, generation_job_id: uuid.UUID) -> None:
        """Close a job whose units were all attempted; failed ones can be resumed."""
        await self.record_progress(generation_job_id)
        job = await self._job(generation_job_id)
        if job.status not in (GenerationStatus.CANCELLED, GenerationStatus.FAILED):
            job.status = GenerationStatus.COMPLETED
        await self.session.flush()

    async def fail_job(self, generation_job_id: uuid.UUID, reason: str) -> None:
        """Record that a job stopped for a reason that is not one of its units."""
        job = await self._job(generation_job_id)
        job.status = GenerationStatus.FAILED
        job.error = reason
        await self.session.flush()

    async def _job(self, generation_job_id: uuid.UUID) -> GenerationJob:
        job = await self.jobs.get_by_id(generation_job_id)
        if job is None:
            raise GenerationJobNotFoundError(generation_job_id)
        return job

    async def _close(self, unit: GenerationUnit, end: str) -> ExecutionStatus:
        unit.status = ExecutionStatus.SUCCEEDED
        unit.end_reason = end
        await self.session.commit()
        return unit.status

    async def _prepare(
        self,
        job: GenerationJob,
        unit: GenerationUnit,
        on_step: Callable[[], None],
    ) -> tuple[UnitScope, str]:
        """The scope of the unit's tools and the request the agent starts from."""
        refs = Refs(job.document_ids)
        existing = list(await self.questions.texts_in_set(job.qa_set_id))
        existing += await self.proposals.texts(job.id)
        limits = {**DEFAULT_LIMITS, **job.params.get("limits", {})}
        remaining = max(0, unit.target - unit.produced)
        if unit.phase is GenerationPhase.DOCUMENT:
            document_id = unit.document_id
            catalogue = await self.texts.catalogue(
                job.chunking_configuration_id, [document_id]
            )
            row = catalogue[document_id]
            unit_zones = zones(row.chunk_count, unit.target)
            scope = UnitScope(
                session=self.session,
                job=job,
                unit=unit,
                refs=refs,
                documents=[document_id],
                existing=existing,
                target=remaining,
                zones=unit_zones,
                tracer=self.tracer,
                on_step=on_step,
            )
            task = document_task(
                target=remaining,
                zones=len(unit_zones),
                document=(
                    f"The document is {refs.document(document_id)} ({row.filename}): "
                    f"{row.text_length} characters, {row.chunk_count} chunks."
                ),
                saved=await self.proposals.texts(job.id, unit_id=unit.id),
            )
            return scope, task

        summaries = {
            item.document_id: (item.summary, list(item.topics or []))
            for item in await self.units.list_by_job(job.id)
            if item.phase is GenerationPhase.DOCUMENT
        }
        scope = UnitScope(
            session=self.session,
            job=job,
            unit=unit,
            refs=refs,
            documents=list(job.document_ids),
            existing=existing,
            target=remaining,
            summaries=summaries,
            tracer=self.tracer,
            on_step=on_step,
        )
        catalogue = await GenerationTools(scope).list_documents(0)
        task = cross_task(
            target=remaining,
            min_documents=int(limits["min_cross_documents"]),
            max_documents=int(limits["max_cross_documents"]),
            catalogue=catalogue,
            delivered=await self._delivered_cross(job, refs),
        )
        return scope, task

    async def _delivered_cross(self, job: GenerationJob, refs: Refs) -> list[str]:
        """The cross questions of the job so far, each with the documents it combines."""
        documents = await self.proposals.documents_by_proposal(job.id)
        delivered = []
        offset = 0
        while True:
            page, total = await self.proposals.list(
                job.id, status=None, kind=None, limit=200, offset=offset
            )
            for proposal in page:
                cited = documents.get(proposal.id)
                if cited is None or len(cited) < 2:
                    continue
                names = ", ".join(sorted(refs.document(d) for d in cited))
                delivered.append(f"{proposal.text} [{names}]")
            offset += len(page)
            if not page or offset >= total:
                return delivered

    async def _metadata(
        self, job: GenerationJob, unit: GenerationUnit
    ) -> dict[str, str]:
        document = None
        if unit.document_id is not None:
            row = (
                await self.texts.catalogue(
                    job.chunking_configuration_id, [unit.document_id]
                )
            ).get(unit.document_id)
            document = row.filename if row else str(unit.document_id)
        values = {
            "generation_job_id": job.id,
            "generation_unit_id": unit.id,
            "qa_set_id": job.qa_set_id,
            "chunking_configuration_id": job.chunking_configuration_id,
            "phase": unit.phase.value,
            "document": document,
            "model": job.params.get("model"),
            "prompt_version": job.prompt_version,
        }
        return {
            key: str(value)[:_MAX_VALUE]
            for key, value in values.items()
            if value is not None
        }
