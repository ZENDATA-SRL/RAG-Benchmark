from pathlib import Path

import pytesseract
from pdf2image import convert_from_path
from PIL import Image

from config.ingestion.ocr.base import BaseOCR


class TesseractOCR(BaseOCR):
    def extract_text(self, file_path: str) -> str:
        path = Path(file_path)
        if path.suffix.lower() != ".pdf":
            with Image.open(path) as im:
                return self._ocr(im)
        chunks: list[str] = []
        for im in convert_from_path(path):
            chunks.append(self._ocr(im))
        return "\n\n".join(c for c in chunks if c)

    def _ocr(self, image: Image.Image) -> str:
        return pytesseract.image_to_string(image).strip()
