from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.experiments.metrics import MetricSpec, metric_specs
from src.experiments.models import Evaluator, MetricDefinition
from src.infrastructure.database.enums import EvaluatorKind, MetricLevel

logger = logging.getLogger(__name__)

# One deterministic evaluator per level: each rewrites only its own scores, and the
# evaluation of a score names what judged it. The call efficiency reads no gold and has no
# level. A metric can name another evaluator, as the answer metrics do.
DETERMINISTIC_EVALUATORS: dict[MetricLevel | None, str] = {
    MetricLevel.DOCUMENT: "document_level_retrieval",
    MetricLevel.CHUNK: "chunk_level_retrieval",
    None: "retrieval_call_efficiency",
}
DETERMINISTIC_EVALUATOR_VERSION = "1"


def evaluator_name(spec: MetricSpec) -> str:
    """The evaluator that scores a metric: its own, or the one of its level."""
    return spec.evaluator or DETERMINISTIC_EVALUATORS[spec.level]


async def seed_metric_catalog(
    session: AsyncSession,
) -> tuple[dict[str, MetricDefinition], dict[str, Evaluator]]:
    """Register the metrics and their deterministic evaluators, idempotently.

    Runs at startup and again before a run is evaluated, so a worker never depends on the
    API having started first. Existing rows are left as they are: a definition that
    changed would alter the meaning of scores already stored.

    Args:
        session: Session owning the transaction; the caller commits.

    Returns:
        The definitions by key and the evaluators by name.
    """
    existing = {
        definition.key: definition
        for definition in await session.scalars(select(MetricDefinition))
    }
    for spec in metric_specs():
        if spec.key in existing:
            continue
        definition = MetricDefinition(
            key=spec.key,
            family=spec.family,
            level=spec.level,
            direction=spec.direction,
            aggregation=spec.aggregation,
            description=spec.description,
        )
        session.add(definition)
        existing[spec.key] = definition

    evaluators = {}
    for name in dict.fromkeys(evaluator_name(spec) for spec in metric_specs()):
        evaluator = await session.scalar(
            select(Evaluator).where(
                Evaluator.kind == EvaluatorKind.DETERMINISTIC,
                Evaluator.name == name,
                Evaluator.version == DETERMINISTIC_EVALUATOR_VERSION,
            )
        )
        if evaluator is None:
            evaluator = Evaluator(
                kind=EvaluatorKind.DETERMINISTIC,
                name=name,
                version=DETERMINISTIC_EVALUATOR_VERSION,
            )
            session.add(evaluator)
        evaluators[name] = evaluator
    await session.flush()
    logger.debug("metric catalog seeded: %d definitions", len(existing))
    return existing, evaluators
