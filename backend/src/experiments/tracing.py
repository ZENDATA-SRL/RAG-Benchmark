from __future__ import annotations

import dataclasses
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.experiments.models import Execution, Experiment, Run
from src.infrastructure.observability import Tracer
from src.pipelines.models import ChunkingConfiguration, ChunkingProfile, ParsingProfile
from src.qa_sets.models import QASet, QASetSnapshot, Question
from src.qa_sets.repository import QuestionRepository

TRACE_NAME = "qa-answer"

# Langfuse keeps trace-level metadata as short strings, so ids and names fit and whole
# configurations do not: those stay in the run's configuration snapshot.
_MAX_VALUE = 200


@dataclasses.dataclass(frozen=True)
class ExecutionTrace:
    """Where an execution is traced and how it is filed in the dataset run of its variant.

    `trace_id` is `None` when tracing is off; `dataset_run_name` is `None` when the run
    has no dataset on Langfuse, and the execution is then traced but not filed.
    """

    trace_id: str | None
    metadata: dict[str, str] = dataclasses.field(default_factory=dict)
    tags: list[str] = dataclasses.field(default_factory=list)
    dataset_name: str | None = None
    dataset_item_id: str | None = None
    dataset_run_name: str | None = None


def dataset_name(qa_set_name: str, snapshot: QASetSnapshot) -> str:
    """The Langfuse dataset of a frozen question set: one per snapshot, never changed."""
    return f"{qa_set_name} · {snapshot.label} · {snapshot.id.hex[:8]}"


def dataset_item_id(snapshot_id: uuid.UUID, question_id: uuid.UUID) -> str:
    """The item of a question in the dataset of a snapshot.

    Item ids are unique across a Langfuse project, and a question belongs to every snapshot
    that froze it, so the id is derived from both.
    """
    return str(uuid.uuid5(snapshot_id, str(question_id)))


def run_name(experiment_name: str, run: Run) -> str:
    """The prefix of the dataset runs of a run; each variant appends its own name."""
    return f"{experiment_name} · {run.created_at:%Y-%m-%d %H:%M} · {run.id.hex[:8]}"


def trace_metadata(
    config_snapshot: dict[str, Any],
    execution: Execution,
    *,
    parsing_profile: str | None,
    chunking_profile: str | None,
) -> dict[str, str]:
    """The configuration that produced an execution, as filterable trace metadata.

    Read from the copy the run took at launch, so a trace describes what ran even if a
    profile was derived or renamed afterwards.
    """
    variant = _variant(config_snapshot, execution.variant_id)
    index_build = variant.get("index_build") or {}
    answer = variant.get("answer_profile") or {}
    params = answer.get("params") or {}
    experiment = config_snapshot.get("experiment") or {}
    values = {
        "experiment_id": experiment.get("id"),
        "run_id": execution.run_id,
        "variant_id": execution.variant_id,
        "variant": variant.get("name"),
        "execution_id": execution.id,
        "question_id": execution.question_id,
        "repetition": execution.repetition,
        "qa_set_snapshot_id": (config_snapshot.get("qa_set_snapshot") or {}).get("id"),
        "corpus_snapshot_id": (config_snapshot.get("corpus_snapshot") or {}).get("id"),
        "index_build_id": index_build.get("id"),
        "chunking_configuration_id": index_build.get("chunking_configuration_id"),
        "parsing_profile": parsing_profile,
        "chunking_profile": chunking_profile,
        "embedding_profile": (variant.get("embedding_profile") or {}).get("name"),
        "vector_store_profile": (variant.get("vector_store_profile") or {}).get("name"),
        "retrieval_profile": (variant.get("retrieval_profile") or {}).get("name"),
        "answer_profile": answer.get("name"),
        "answer_system": answer.get("component"),
        "model": params.get("model"),
        "retrieval_scope": experiment.get("retrieval_scope"),
    }
    return {
        key: str(value)[:_MAX_VALUE]
        for key, value in values.items()
        if value is not None
    }


def trace_tags(config_snapshot: dict[str, Any], execution: Execution) -> list[str]:
    """Tags that group the traces of an experiment and of each of its variants."""
    experiment = (config_snapshot.get("experiment") or {}).get("name")
    variant = _variant(config_snapshot, execution.variant_id).get("name")
    tags = [f"experiment:{experiment}" if experiment else None]
    tags.append(f"variant:{variant}" if variant else None)
    return [tag[:_MAX_VALUE] for tag in tags if tag]


def _variant(config_snapshot: dict[str, Any], variant_id: uuid.UUID) -> dict[str, Any]:
    for variant in config_snapshot.get("variants") or []:
        if variant.get("id") == str(variant_id):
            return variant
    return {}


class ExperimentTracing:
    """Files the traces of a Q&A run under a Langfuse dataset and its dataset runs.

    The frozen question set is a dataset, each variant of a run a dataset run, and each
    execution an item of it: Langfuse's own comparison of runs then lines up the same
    questions the platform compares. Everything here is best-effort, as the tracer is.
    """

    def __init__(self, session: AsyncSession, tracer: Tracer) -> None:
        self.session = session
        self.tracer = tracer

    async def open_run(self, run_id: uuid.UUID) -> None:
        """Make sure the run's question set has a dataset and the run a name for its runs.

        The dataset is created once per snapshot and its id kept on it; a run whose
        dataset could not be created gets no name, and a resumed run tries again.
        """
        if not self.tracer.enabled:
            return
        run = await self.session.get(Run, run_id)
        experiment = await self.session.get(Experiment, run.experiment_id)
        snapshot = await self.session.get(QASetSnapshot, experiment.qa_set_snapshot_id)
        if snapshot.langfuse_dataset_id is None:
            qa_set = await self.session.get(QASet, snapshot.qa_set_id)
            snapshot.langfuse_dataset_id = await self.tracer.create_dataset(
                dataset_name(qa_set.name, snapshot),
                description=f"Questions of {qa_set.name!r} frozen as {snapshot.label!r}",
                metadata={
                    "qa_set_id": str(qa_set.id),
                    "qa_set_snapshot_id": str(snapshot.id),
                    "composition_hash": snapshot.composition_hash,
                },
            )
        if snapshot.langfuse_dataset_id is not None and run.langfuse_run_name is None:
            run.langfuse_run_name = run_name(experiment.name, run)
        await self.session.flush()

    async def for_execution(self, execution: Execution) -> ExecutionTrace:
        """The trace id, metadata, tags and dataset run of an execution."""
        trace_id = self.tracer.trace_id(str(execution.id))
        if trace_id is None:
            return ExecutionTrace(trace_id=None)
        run = await self.session.get(Run, execution.run_id)
        variant = _variant(run.config_snapshot, execution.variant_id)
        configuration_id = (variant.get("index_build") or {}).get(
            "chunking_configuration_id"
        )
        parsing, chunking = await self._profile_names(configuration_id)
        trace = ExecutionTrace(
            trace_id=trace_id,
            metadata=trace_metadata(
                run.config_snapshot,
                execution,
                parsing_profile=parsing,
                chunking_profile=chunking,
            ),
            tags=trace_tags(run.config_snapshot, execution),
        )
        if run.langfuse_run_name is None:
            return trace
        experiment = await self.session.get(Experiment, run.experiment_id)
        snapshot = await self.session.get(QASetSnapshot, experiment.qa_set_snapshot_id)
        if snapshot.langfuse_dataset_id is None:
            return trace
        qa_set = await self.session.get(QASet, snapshot.qa_set_id)
        return dataclasses.replace(
            trace,
            dataset_name=dataset_name(qa_set.name, snapshot),
            dataset_item_id=dataset_item_id(snapshot.id, execution.question_id),
            dataset_run_name=f"{run.langfuse_run_name} · {variant.get('name', '')}",
        )

    async def file(
        self,
        trace: ExecutionTrace,
        question: Question,
        execution: Execution,
        observation_id: str | None,
    ) -> None:
        """File an execution's trace as the outcome of its question in the variant's run.

        The question's item is written first, by its derived id, so items appear as
        executions reach them and a run never has to copy the whole set up front.
        """
        if (
            trace.trace_id is None
            or trace.dataset_run_name is None
            or trace.dataset_name is None
            or trace.dataset_item_id is None
        ):
            return
        expected = (
            await QuestionRepository(self.session).answers_by_question([question.id])
        ).get(question.id, [])
        written = await self.tracer.upsert_dataset_item(
            trace.dataset_name,
            trace.dataset_item_id,
            input={"question": question.text},
            expected_output={"answer": expected[0].text} if expected else None,
            metadata={
                "question_id": str(question.id),
                "answerable": question.answerable,
                "tags": list(question.tags),
            },
        )
        if not written:
            return
        await self.tracer.link_dataset_run(
            trace.dataset_run_name,
            trace.dataset_item_id,
            trace_id=trace.trace_id,
            observation_id=observation_id,
            metadata={
                "execution_id": str(execution.id),
                "repetition": execution.repetition,
            },
        )

    async def _profile_names(
        self, configuration_id: str | None
    ) -> tuple[str | None, str | None]:
        if configuration_id is None:
            return None, None
        configuration = await self.session.get(
            ChunkingConfiguration, uuid.UUID(configuration_id)
        )
        if configuration is None:
            return None, None
        parsing = await self.session.get(
            ParsingProfile, configuration.parsing_profile_id
        )
        chunking = await self.session.get(
            ChunkingProfile, configuration.chunking_profile_id
        )
        return (
            parsing.name if parsing else None,
            chunking.name if chunking else None,
        )
