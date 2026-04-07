from uuid import UUID

from core.models import Chunk, Embedding, Scan


async def get_scan(ocr_id: UUID, document_id: UUID) -> Scan | None:
    pass


async def insert_scan(scan: Scan) -> None:
    pass


async def get_chunks(chunker_id: UUID, scan_id: UUID) -> list[Chunk]:
    pass


async def insert_chunks(chunker_id: UUID, chunks: list[Chunk]) -> None:
    pass


async def get_embeddings(
    embedder_id: UUID, chunker_id: UUID, scan_id: UUID
) -> list[Embedding]:
    pass


async def insert_embeddings(embeddings: list[Embedding]) -> None:
    pass
