from io import BytesIO

from pypdf import PdfReader

from config.ingestion.ocr.base import BaseOCR


class PypdfOCR(BaseOCR):
    """Extract selectable text from PDFs via pypdf (no OCR for scans or raster images)."""

    async def extract_text(self, document_bytes: bytes) -> str:
        reader = PdfReader(BytesIO(document_bytes))
        parts: list[str] = []
        for page in reader.pages:
            raw = page.extract_text()
            if raw:
                stripped = raw.strip()
                if stripped:
                    parts.append(stripped)
        return "\n\n".join(parts)
