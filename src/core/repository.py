from uuid import UUID

from sqlalchemy import select

from src.core.schemas import Experiment
from src.core.models import AnswerORM, ChunkORM, EmbeddingORM, ExperimentORM, ScanORM
from src.infrastructure.database.db import get_sessionmaker


async def get_scan(ocr_id: UUID, document_id: UUID) -> ScanORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(ScanORM)
            .where(ScanORM.ocr_id == ocr_id)
            .where(ScanORM.document_id == document_id)
            .limit(1)
        )
        return await session.scalar(stmt)


async def insert_scan(scan: ScanORM) -> None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(scan)
        await session.commit()
        await session.refresh(scan)


async def get_chunks(chunker_id: UUID, scan_id: UUID) -> list[ChunkORM]:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(ChunkORM)
            .where(ChunkORM.chunker_id == chunker_id)
            .where(ChunkORM.scan_id == scan_id)
            .order_by(ChunkORM.start_index.asc())
        )
        rows = (await session.scalars(stmt)).all()
        return list(rows)


async def insert_chunks(chunker_id: UUID, chunks: list[ChunkORM]) -> None:
    if not chunks:
        return
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add_all(chunks)
        await session.commit()


async def get_embeddings(
    embedder_id: UUID, chunker_id: UUID, scan_id: UUID
) -> list[EmbeddingORM]:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(EmbeddingORM)
            .join(EmbeddingORM.chunk)
            .where(EmbeddingORM.embedder_id == embedder_id)
            .where(ChunkORM.chunker_id == chunker_id)
            .where(ChunkORM.scan_id == scan_id)
            .order_by(ChunkORM.start_index.asc())
        )
        rows = (await session.scalars(stmt)).all()
        return list(rows)


async def insert_embeddings(embeddings: list[EmbeddingORM]) -> None:
    if not embeddings:
        return
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add_all(embeddings)
        await session.commit()


async def get_experiment_by_id(experiment_id: UUID) -> ExperimentORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        return await session.get(ExperimentORM, experiment_id)


async def get_experiments() -> list[ExperimentORM]:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = select(ExperimentORM).order_by(ExperimentORM.created_at.desc())
        rows = (await session.scalars(stmt)).all()
        return list(rows)


async def insert_experiment(experiment: ExperimentORM) -> Experiment:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(experiment)
        await session.commit()
        await session.refresh(experiment)
        return Experiment.model_validate(experiment)


async def update_experiment(experiment: Experiment) -> Experiment:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        orm = await session.get(ExperimentORM, experiment.id)
        if orm is None:
            raise ValueError(f"Experiment {experiment.id} not found")
        orm.dataset_run_id = experiment.dataset_run_id
        orm.langfuse_experiment_id = experiment.langfuse_experiment_id
        await session.commit()
        await session.refresh(orm)
        return Experiment.model_validate(orm)


async def get_answers(experiment_id: UUID) -> list[AnswerORM]:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = select(AnswerORM).where(AnswerORM.experiment_id == experiment_id)
        rows = (await session.scalars(stmt)).all()
        return list(rows)


async def insert_answer(answer: AnswerORM) -> None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(answer)
        await session.commit()
        await session.refresh(answer)
