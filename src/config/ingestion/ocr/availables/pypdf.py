from pathlib import Path

from pypdf import PdfReader

from config.ingestion.ocr.base import BaseOCR


class PypdfOCR(BaseOCR):
    """Extract selectable text from PDFs via pypdf (no OCR for scans or raster images)."""

    def extract_text(self, file_path: str) -> str:
        path = Path(file_path)
        if path.suffix.lower() != ".pdf":
            raise ValueError("Pypdf only supports .pdf files")

        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages:
            raw = page.extract_text()
            if raw:
                stripped = raw.strip()
                if stripped:
                    parts.append(stripped)
        return "\n\n".join(parts)
