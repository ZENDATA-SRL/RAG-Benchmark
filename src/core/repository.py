from uuid import UUID

from core.models import ChunkORM, EmbeddingORM, ScanORM
from infrastructure.database.db import get_sessionmaker

from sqlalchemy import select


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
