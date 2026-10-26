from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.experiments.metrics import metric_specs
from src.experiments.models import Evaluator, MetricDefinition
from src.infrastructure.database.enums import EvaluatorKind, MetricFamily, MetricLevel

logger = logging.getLogger(__name__)

# One deterministic evaluator per level: each rewrites only its own scores, and the
# evaluation of a score names what judged it.
DETERMINISTIC_EVALUATORS = {
    MetricLevel.DOCUMENT: "document_level_retrieval",
    MetricLevel.CHUNK: "chunk_level_retrieval",
}
DETERMINISTIC_EVALUATOR_VERSION = "1"


async def seed_metric_catalog(
    session: AsyncSession,
) -> tuple[dict[str, MetricDefinition], dict[MetricLevel, Evaluator]]:
    """Register the retrieval metrics and their deterministic evaluators, idempotently.

    Runs at startup and again before a run is evaluated, so a worker never depends on the
    API having started first. Existing rows are left as they are: a definition that
    changed would alter the meaning of scores already stored.

    Args:
        session: Session owning the transaction; the caller commits.

    Returns:
        The definitions by key and the evaluator of each level.
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
            family=MetricFamily.RETRIEVAL,
            level=spec.level,
            direction=spec.direction,
            aggregation=spec.aggregation,
            description=spec.description,
        )
        session.add(definition)
        existing[spec.key] = definition

    evaluators = {}
    for level, name in DETERMINISTIC_EVALUATORS.items():
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
        evaluators[level] = evaluator
    await session.flush()
    logger.debug("metric catalog seeded: %d definitions", len(existing))
    return existing, evaluators
