from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from src.evals.models import BenchmarkORM, EvaluationORM
from src.infrastructure.database.db import get_sessionmaker


async def get_benchmark(benchmark_id: UUID) -> BenchmarkORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        return await session.get(BenchmarkORM, benchmark_id)


async def get_benchmarks() -> list[BenchmarkORM]:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = select(BenchmarkORM).order_by(BenchmarkORM.created_at.desc())
        rows = (await session.scalars(stmt)).all()
        return list(rows)


async def find_benchmark_by_name(name: str) -> BenchmarkORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = select(BenchmarkORM).where(BenchmarkORM.name == name).limit(1)
        return await session.scalar(stmt)


async def insert_benchmark(benchmark: BenchmarkORM) -> None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(benchmark)
        await session.commit()
        await session.refresh(benchmark)


async def get_evaluation(evaluation_id: UUID) -> EvaluationORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        return await session.get(EvaluationORM, evaluation_id)


async def get_evaluations_by_benchmark(benchmark_id: UUID) -> list[EvaluationORM]:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(EvaluationORM)
            .where(EvaluationORM.benchmark_id == benchmark_id)
            .order_by(EvaluationORM.created_at.desc())
        )
        rows = (await session.scalars(stmt)).all()
        return list(rows)


async def find_evaluation(
    *, benchmark_id: UUID, question_id: UUID, answer_id: UUID
) -> EvaluationORM | None:
    """
    Finds an evaluation for a (benchmark, question, answer) triple.
    Useful to avoid creating duplicates when re-running evaluations.
    """
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(EvaluationORM)
            .where(EvaluationORM.benchmark_id == benchmark_id)
            .where(EvaluationORM.question_id == question_id)
            .where(EvaluationORM.answer_id == answer_id)
            .limit(1)
        )
        return await session.scalar(stmt)


async def insert_evaluation(evaluation: EvaluationORM) -> None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(evaluation)
        await session.commit()
        await session.refresh(evaluation)
