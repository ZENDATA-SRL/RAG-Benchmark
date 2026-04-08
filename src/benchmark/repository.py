from uuid import UUID

from benchmark.models import BenchmarkORM, DocumentORM, QuestionORM
from infrastructure.database.db import get_sessionmaker

from sqlalchemy import select


async def get_document(document_id: UUID) -> DocumentORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        return await session.get(DocumentORM, document_id)


async def find_document_by_name_and_url(
    name: str, url: str, benchmark_id: UUID
) -> DocumentORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(DocumentORM)
            .where(DocumentORM.name == name)
            .where(DocumentORM.url == url)
            .where(DocumentORM.benchmark_id == benchmark_id)
            .limit(1)
        )
        return await session.scalar(stmt)


async def insert_document(document: DocumentORM) -> None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(document)
        await session.commit()
        await session.refresh(document)

async def get_benchmark(benchmark_id: UUID) -> BenchmarkORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        return await session.get(BenchmarkORM, benchmark_id)

async def get_question(question_id: UUID) -> QuestionORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        return await session.get(QuestionORM, question_id)

async def insert_benchmark(benchmark: BenchmarkORM) -> None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(benchmark)
        await session.commit()
        await session.refresh(benchmark)


async def insert_question(question: QuestionORM) -> None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(question)
        await session.commit()
        await session.refresh(question)
