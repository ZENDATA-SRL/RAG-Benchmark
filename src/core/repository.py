from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload

from src.core.models import (
    AnswerChunkORM,
    AnswerORM,
    ChunkORM,
    EmbeddingORM,
    ExperimentORM,
    ScanORM,
)
from src.core.schemas import Experiment
from src.dataset.models import DocumentORM, QuestionORM
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


async def get_answer_by_question_and_experiment_id(
    question_id: UUID, experiment_id: UUID
) -> AnswerORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        return await session.scalar(
            select(AnswerORM)
            .where(AnswerORM.question_id == question_id)
            .where(AnswerORM.experiment_id == experiment_id)
            .limit(1)
        )


async def insert_answer(answer: AnswerORM) -> None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(answer)
        await session.commit()
        await session.refresh(answer)


async def insert_answer_chunks(answer_chunks: list[AnswerChunkORM]) -> None:
    if not answer_chunks:
        return
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add_all(answer_chunks)
        await session.commit()


async def get_question_document_chunk_coverage(experiment_id: UUID) -> list[dict]:
    """
    Computed stats (not persisted) for an experiment:
    for each question, report whether answer used chunks from that question's document.
    """
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        used_from_doc = case(
            (ScanORM.document_id == QuestionORM.document_id, AnswerChunkORM.id),
            else_=None,
        )
        stmt = (
            select(
                QuestionORM.id.label("question_id"),
                QuestionORM.query.label("question"),
                DocumentORM.id.label("document_id"),
                DocumentORM.name.label("document_name"),
                DocumentORM.url.label("document_url"),
                func.count(func.distinct(AnswerChunkORM.id)).label(
                    "total_answer_chunks"
                ),
                func.count(func.distinct(used_from_doc)).label(
                    "answer_chunks_from_document"
                ),
            )
            .select_from(AnswerORM)
            .join(QuestionORM, AnswerORM.question_id == QuestionORM.id)
            .join(DocumentORM, QuestionORM.document_id == DocumentORM.id)
            .outerjoin(AnswerChunkORM, AnswerChunkORM.answer_id == AnswerORM.id)
            .outerjoin(ChunkORM, AnswerChunkORM.chunk_id == ChunkORM.id)
            .outerjoin(ScanORM, ChunkORM.scan_id == ScanORM.id)
            .where(AnswerORM.experiment_id == experiment_id)
            .group_by(
                QuestionORM.id,
                QuestionORM.query,
                DocumentORM.id,
                DocumentORM.name,
                DocumentORM.url,
            )
            .order_by(QuestionORM.id.asc())
        )
        rows = (await session.execute(stmt)).mappings().all()
        return [dict(r) for r in rows]


async def get_experiments_by_dataset_id(dataset_id: UUID) -> list[ExperimentORM]:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(ExperimentORM)
            .where(ExperimentORM.dataset_id == dataset_id)
            .options(
                selectinload(ExperimentORM.rag_config),
                selectinload(ExperimentORM.answers).selectinload(AnswerORM.trace),
            )
        )
        rows = (await session.scalars(stmt)).all()
        return list(rows)
