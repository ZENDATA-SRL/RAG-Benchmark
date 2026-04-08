from uuid import UUID

from config.ingestion.ocr.models import OCRConfig
from config.ingestion.ocr.schemas import OCRConfigSchema
from infrastructure.database.db import get_sessionmaker

from sqlalchemy import select


class OCRRepository:
    async def get_ocr_by_id(self, ocr_id: UUID) -> OCRConfig | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            return await session.get(OCRConfig, ocr_id)

    async def get_ocr_by_config(self, ocr: OCRConfigSchema) -> OCRConfig | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            stmt = select(OCRConfig).where(OCRConfig.model == ocr.model).limit(1)
            return await session.scalar(stmt)

    async def insert_ocr_config(self, ocr: OCRConfigSchema) -> OCRConfig:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            obj = OCRConfig(model=ocr.model)
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj


def get_ocr_repository() -> OCRRepository:
    return OCRRepository()
