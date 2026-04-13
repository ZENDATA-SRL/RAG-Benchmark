from uuid import UUID

from sqlalchemy import select

from src.core.models import ChunkORM, EmbeddingORM, ScanORM
from src.dataset.models import DocumentORM
from src.infrastructure.database.db import get_sessionmaker
from src.infrastructure.vectordb.models import EmbeddedChunk


async def chunk_ids_for_dataset(
    *,
    dataset_id: UUID,
    ocr_id: UUID,
    chunker_id: UUID,
) -> list[UUID]:
    """
    Return chunk IDs such that:
    - Chunk.scan_id -> Scan.document_id -> Document.dataset_id == dataset_id
    - Scan.ocr_id == ocr_id
    - Chunk.chunker_id == chunker_id
    """

    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(ChunkORM.id)
            .join(ScanORM, ScanORM.id == ChunkORM.scan_id)
            .join(DocumentORM, DocumentORM.id == ScanORM.document_id)
            .where(DocumentORM.dataset_id == dataset_id)
            .where(ScanORM.ocr_id == ocr_id)
            .where(ChunkORM.chunker_id == chunker_id)
        )
        rows = (await session.scalars(stmt)).all()
    return list(rows)


async def embedded_chunks_for_chunk_ids(
    *,
    chunk_ids: list[UUID],
    embedder_id: UUID,
) -> list[EmbeddedChunk]:
    """
    Load embedded chunks from Postgres to be (re)uploaded to the vector DB.
    """

    if not chunk_ids:
        return []

    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(EmbeddingORM.id, EmbeddingORM.chunk_id, EmbeddingORM.embedder_id, EmbeddingORM.vectors, ChunkORM.text)
            .join(ChunkORM, ChunkORM.id == EmbeddingORM.chunk_id)
            .where(EmbeddingORM.embedder_id == embedder_id)
            .where(EmbeddingORM.chunk_id.in_(chunk_ids))
        )
        rows = (await session.execute(stmt)).all()

    out: list[EmbeddedChunk] = []
    for emb_id, chunk_id, emb_embedder_id, vectors, text in rows:
        out.append(
            EmbeddedChunk(
                id=emb_id,
                embedding_id=emb_id,
                chunk_id=chunk_id,
                text=text,
                vectors=list(vectors or []),
            )
        )
    return out

