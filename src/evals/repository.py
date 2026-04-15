from __future__ import annotations

import logging
import time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.evals.models import EvaluatorORM, ScoreORM, TraceORM
from src.infrastructure.database.db import get_sessionmaker

logger = logging.getLogger(__name__)


async def get_evaluator_by_name(name: str) -> EvaluatorORM | None:
    t0 = time.perf_counter()
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = select(EvaluatorORM).where(EvaluatorORM.name == name).limit(1)
        obj = await session.scalar(stmt)
        logger.debug(
            "evals.repo.get_evaluator_by_name",
            extra={
                "event": "evals.repo.get_evaluator_by_name",
                "item_name": name,
                "found": bool(obj),
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
            },
        )
        return obj


async def get_evaluator_by_id(id: UUID) -> EvaluatorORM | None:
    t0 = time.perf_counter()
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = select(EvaluatorORM).where(EvaluatorORM.id == id).limit(1)
        obj = await session.scalar(stmt)
        logger.debug(
            "evals.repo.get_evaluator_by_id",
            extra={
                "event": "evals.repo.get_evaluator_by_id",
                "evaluator_id": str(id),
                "found": bool(obj),
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
            },
        )
        return obj


async def create_evaluator(name: str) -> EvaluatorORM:
    t0 = time.perf_counter()
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        obj = EvaluatorORM(name=name)
        session.add(obj)
        try:
            await session.commit()
            await session.refresh(obj)
        except Exception:
            logger.exception(
                "evals.repo.create_evaluator.failed",
                extra={"event": "evals.repo.create_evaluator.failed", "name": name},
            )
            raise
        logger.info(
            "evals.repo.create_evaluator.complete",
            extra={
                "event": "evals.repo.create_evaluator.complete",
                "item_name": name,
                "evaluator_id": str(obj.id),
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
            },
        )
        return obj


async def get_trace_by_answer_id(answer_id: UUID) -> TraceORM | None:
    t0 = time.perf_counter()
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = select(TraceORM).where(TraceORM.answer_id == answer_id).limit(1)
        obj = await session.scalar(stmt)
        logger.debug(
            "evals.repo.get_trace_by_answer_id",
            extra={
                "event": "evals.repo.get_trace_by_answer_id",
                "answer_id": str(answer_id),
                "found": bool(obj),
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
            },
        )
        return obj


async def get_trace_by_langfuse_trace_id(langfuse_trace_id: str) -> TraceORM | None:
    t0 = time.perf_counter()
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(TraceORM)
            .where(TraceORM.langfuse_trace_id == langfuse_trace_id)
            .limit(1)
        )
        obj = await session.scalar(stmt)
        logger.debug(
            "evals.repo.get_trace_by_langfuse_trace_id",
            extra={
                "event": "evals.repo.get_trace_by_langfuse_trace_id",
                "langfuse_trace_id": str(langfuse_trace_id),
                "found": bool(obj),
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
            },
        )
        return obj


async def insert_trace(trace: TraceORM) -> TraceORM:
    t0 = time.perf_counter()
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(trace)
        try:
            await session.commit()
            await session.refresh(trace)
        except Exception:
            logger.exception(
                "evals.repo.insert_trace.failed",
                extra={
                    "event": "evals.repo.insert_trace.failed",
                    "answer_id": str(trace.answer_id),
                    "langfuse_trace_id": str(trace.langfuse_trace_id),
                },
            )
            raise
        logger.debug(
            "evals.repo.insert_trace.complete",
            extra={
                "event": "evals.repo.insert_trace.complete",
                "trace_id": str(trace.id),
                "answer_id": str(trace.answer_id),
                "langfuse_trace_id": str(trace.langfuse_trace_id),
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
            },
        )
        return trace


async def get_score_by_trace_id_and_evaluator_id(
    trace_id: UUID, evaluator_id: UUID
) -> ScoreORM | None:
    t0 = time.perf_counter()
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(ScoreORM)
            .where(ScoreORM.trace_id == trace_id)
            .where(ScoreORM.evaluator_id == evaluator_id)
            .limit(1)
        )
        obj = await session.scalar(stmt)
        logger.debug(
            "evals.repo.get_score_by_trace_id_and_evaluator_id",
            extra={
                "event": "evals.repo.get_score_by_trace_id_and_evaluator_id",
                "trace_id": str(trace_id),
                "evaluator_id": str(evaluator_id),
                "found": bool(obj),
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
            },
        )
        return obj


async def insert_score(score: ScoreORM) -> ScoreORM:
    t0 = time.perf_counter()
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(score)
        try:
            await session.commit()
            await session.refresh(score)
        except Exception:
            logger.exception(
                "evals.repo.insert_score.failed",
                extra={
                    "event": "evals.repo.insert_score.failed",
                    "trace_id": str(score.trace_id),
                    "evaluator_id": str(score.evaluator_id),
                },
            )
            raise
        logger.debug(
            "evals.repo.insert_score.complete",
            extra={
                "event": "evals.repo.insert_score.complete",
                "score_id": str(score.id),
                "trace_id": str(score.trace_id),
                "evaluator_id": str(score.evaluator_id),
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
            },
        )
        return score


async def get_scores_by_trace_id(trace_id: UUID) -> list[ScoreORM]:
    t0 = time.perf_counter()
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(ScoreORM)
            .where(ScoreORM.trace_id == trace_id)
            .options(selectinload(ScoreORM.evaluator))
        )
        rows = (await session.scalars(stmt)).all()
        result = list(rows)
        logger.debug(
            "evals.repo.get_scores_by_trace_id",
            extra={
                "event": "evals.repo.get_scores_by_trace_id",
                "trace_id": str(trace_id),
                "score_count": len(result),
                "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
            },
        )
        return result
