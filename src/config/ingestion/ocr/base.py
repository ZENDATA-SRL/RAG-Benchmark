from abc import ABC, abstractmethod


class BaseOCR(ABC):
    @abstractmethod
    async def extract_text(self, document_bytes: bytes) -> str:
        """Extract text from a PDF (or image bytes for OCR backends that support it)."""
        pass
