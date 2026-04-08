from uuid import UUID

from config.ingestion.ocr.models import OCRConfig
from config.ingestion.ocr.schemas import OCRConfigSchema


class OCRRepository:
    async def get_ocr_by_id(self, ocr_id: UUID) -> OCRConfig | None:
        pass

    async def get_ocr_by_config(self, ocr: OCRConfigSchema) -> OCRConfig | None:
        pass

    async def insert_ocr_config(self, ocr: OCRConfigSchema) -> OCRConfig:
        pass


def get_ocr_repository() -> OCRRepository:
    return OCRRepository()
