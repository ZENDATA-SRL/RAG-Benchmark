from uuid import UUID

from sqlalchemy import select

from src.config.ingestion.ocr.models import OCRConfigORM
from src.config.ingestion.ocr.schemas import OCRConfigSchema
from src.infrastructure.database.db import get_sessionmaker


class OCRRepository:
    async def get_ocr_by_id(self, ocr_id: UUID) -> OCRConfigORM | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            return await session.get(OCRConfigORM, ocr_id)

    async def get_ocr_by_config(self, ocr: OCRConfigSchema) -> OCRConfigORM | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            stmt = select(OCRConfigORM).where(OCRConfigORM.model == ocr.model).limit(1)
            return await session.scalar(stmt)

    async def insert_ocr_config(self, ocr: OCRConfigSchema) -> OCRConfigORM:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            obj = OCRConfigORM(model=ocr.model)
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj


def get_ocr_repository() -> OCRRepository:
    return OCRRepository()
