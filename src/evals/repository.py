from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from src.evals.models import EvaluatorORM, ScoreORM, TraceORM
from src.infrastructure.database.db import get_sessionmaker


async def get_evaluator_by_name(name: str) -> EvaluatorORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = select(EvaluatorORM).where(EvaluatorORM.name == name).limit(1)
        return await session.scalar(stmt)


async def get_evaluator_by_id(id: UUID) -> EvaluatorORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = select(EvaluatorORM).where(EvaluatorORM.id == id).limit(1)
        return await session.scalar(stmt)


async def create_evaluator(name: str) -> EvaluatorORM:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        obj = EvaluatorORM(name=name)
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
        return obj


async def get_trace_by_answer_id(answer_id: UUID) -> TraceORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = select(TraceORM).where(TraceORM.answer_id == answer_id).limit(1)
        return await session.scalar(stmt)


async def get_trace_by_langfuse_trace_id(langfuse_trace_id: str) -> TraceORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(TraceORM)
            .where(TraceORM.langfuse_trace_id == langfuse_trace_id)
            .limit(1)
        )
        return await session.scalar(stmt)


async def insert_trace(trace: TraceORM) -> TraceORM:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(trace)
        await session.commit()
        await session.refresh(trace)
        return trace


async def insert_score(score: ScoreORM) -> ScoreORM:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(score)
        await session.commit()
        await session.refresh(score)
        return score


async def get_scores_by_trace_id(trace_id: UUID) -> list[ScoreORM]:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = select(ScoreORM).where(ScoreORM.trace_id == trace_id)
        rows = (await session.scalars(stmt)).all()
        return list(rows)
