from uuid import UUID

from fastapi import APIRouter

from src.config.ingestion.ocr.schemas import OCRConfig, OCRConfigSchema
from src.config.ingestion.ocr.service import get_ocr_by_id, resolve_ocr

router = APIRouter(prefix="/ocr", tags=["ocr"])


@router.post("")
async def resolve_ocr_route(ocr: OCRConfigSchema) -> OCRConfig:
    return await resolve_ocr(ocr)


@router.get("/{ocr_id}")
async def get_ocr_route(ocr_id: UUID) -> OCRConfig:
    return await get_ocr_by_id(ocr_id)
