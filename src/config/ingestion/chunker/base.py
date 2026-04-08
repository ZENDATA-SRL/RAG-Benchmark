from abc import ABC, abstractmethod
from uuid import UUID

from src.benchmark.schemas import Chunk


class BaseChunker(ABC):
    def __init__(self, chunk_size: int, overlap_size: int) -> None:
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size

    @abstractmethod
    def extract_chunks(self, text: str, scan_id: UUID, chunker_id: UUID) -> list[Chunk]:
        """Chunker carries sizes for execution; persisted recipe is ConfigInput.chunking."""
        pass
