from uuid import UUID

from core.repository import (
    get_chunks as get_chunks_orm,
    get_embeddings as get_embeddings_orm,
    get_scan as get_scan_orm,
    insert_chunks as insert_chunks_orm,
    insert_embeddings as insert_embeddings_orm,
    insert_scan as insert_scan_orm,
)
from core.models import ChunkORM, EmbeddingORM, ScanORM
from core.schemas import Chunk, Embedding, Scan


async def get_scan(ocr_id: UUID, document_id: UUID) -> Scan | None:
    obj = await get_scan_orm(ocr_id=ocr_id, document_id=document_id)
    if obj is None:
        return None
    return Scan.model_validate(obj)


async def insert_scan(scan: ScanORM) -> None:
    await insert_scan_orm(scan)


async def get_chunks(chunker_id: UUID, scan_id: UUID) -> list[Chunk]:
    rows = await get_chunks_orm(chunker_id=chunker_id, scan_id=scan_id)
    return [Chunk.model_validate(r) for r in rows]


async def insert_chunks(chunker_id: UUID, chunks: list[ChunkORM]) -> None:
    await insert_chunks_orm(chunker_id=chunker_id, chunks=chunks)


async def get_embeddings(
    embedder_id: UUID, chunker_id: UUID, scan_id: UUID
) -> list[Embedding]:
    rows = await get_embeddings_orm(
        embedder_id=embedder_id, chunker_id=chunker_id, scan_id=scan_id
    )
    return [Embedding.model_validate(r) for r in rows]


async def insert_embeddings(embeddings: list[EmbeddingORM]) -> None:
    await insert_embeddings_orm(embeddings=embeddings)

