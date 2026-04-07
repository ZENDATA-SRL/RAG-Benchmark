from io import BytesIO

import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image

from config.ingestion.ocr.base import BaseOCR


class TesseractOCR(BaseOCR):
    async def extract_text(self, document_bytes: bytes) -> str:
        if document_bytes[:4] == b"%PDF":
            chunks: list[str] = []
            for im in convert_from_bytes(document_bytes):
                chunks.append(self._ocr(im))
            return "\n\n".join(c for c in chunks if c)
        with Image.open(BytesIO(document_bytes)) as im:
            return self._ocr(im)

    def _ocr(self, image: Image.Image) -> str:
        return pytesseract.image_to_string(image).strip()
