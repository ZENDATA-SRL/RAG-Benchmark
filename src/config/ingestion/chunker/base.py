from abc import ABC, abstractmethod
from typing import List
from uuid import UUID

from core.models import Chunk


class BaseChunker(ABC):
    def __init__(self, chunk_size: int, overlap_size: int) -> None:
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size

    @abstractmethod
    def extract_chunks(
        self, text: str, scan_id: UUID, chunker_id: UUID
    ) -> List[Chunk]:
        """Chunker carries sizes for execution; persisted recipe is ConfigInput.chunking."""
        pass
