from uuid import UUID

from config.ingestion.ocr.availables.azure_document_intelligence import (
    AzureDocumentIntelligenceOCR,
)
from config.ingestion.ocr.availables.easyocr import GeminiOCR
from config.ingestion.ocr.availables.pypdf import PypdfOCR
from config.ingestion.ocr.base import BaseOCR
from config.ingestion.ocr.repository import get_ocr_repository
from config.ingestion.ocr.schemas import OCRConfig, OCRConfigSchema


async def resolve_ocr(ocr: OCRConfigSchema) -> OCRConfig:
    repository = get_ocr_repository()
    ocr_object = await repository.get_ocr_by_config(ocr)
    if ocr_object:
        return OCRConfig.model_validate(ocr_object)
    created = await repository.insert_ocr_config(ocr)
    return OCRConfig.model_validate(created)


async def get_ocr_by_id(ocr_id: UUID) -> OCRConfig:
    repository = get_ocr_repository()
    obj = await repository.get_ocr_by_id(ocr_id)
    if obj is None:
        raise ValueError(f"OCR config {ocr_id} not found")
    return OCRConfig.model_validate(obj)


def build_ocr(ocr: OCRConfigSchema) -> BaseOCR:
    if ocr.model == "easyocr":
        return GeminiOCR()
    elif ocr.model == "pypdf":
        return PypdfOCR()
    elif ocr.model == "azure_document_intelligence":
        return AzureDocumentIntelligenceOCR()
    else:
        raise ValueError(f"Unknown OCR model: {ocr.model}")
