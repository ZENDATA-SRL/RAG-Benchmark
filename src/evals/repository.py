from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from src.evals.models import LangfuseEvaluationORM, RagEvaluationORM
from src.infrastructure.database.db import get_sessionmaker


async def get_rag_evaluation(evaluation_id: UUID) -> RagEvaluationORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        return await session.get(RagEvaluationORM, evaluation_id)


async def get_rag_evaluations_by_experiment(
    experiment_id: UUID,
) -> list[RagEvaluationORM]:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(RagEvaluationORM)
            .where(RagEvaluationORM.experiment_id == experiment_id)
            .order_by(RagEvaluationORM.created_at.desc())
        )
        rows = (await session.scalars(stmt)).all()
        return list(rows)


async def insert_rag_evaluation(evaluation: RagEvaluationORM) -> None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(evaluation)
        await session.commit()
        await session.refresh(evaluation)


async def get_langfuse_evaluation(
    experiment_id: UUID,
) -> LangfuseEvaluationORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        return await session.get(LangfuseEvaluationORM, experiment_id)


async def insert_langfuse_evaluation(evaluation: LangfuseEvaluationORM) -> None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(evaluation)
        await session.commit()
        await session.refresh(evaluation)
