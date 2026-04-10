import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile

from src.dataset.models import DatasetORM
from src.dataset.repository import (
    delete_dataset,
    get_dataset,
    get_datasets,
    insert_dataset,
)
from src.dataset.schemas import Dataset, DatasetCreate
from src.dataset.service import (
    DocumentNotFoundError,
    get_documents,
    get_questions,
    ingest_dataset_questions,
    ingest_documents_from_file,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dataset", tags=["dataset"])


@router.post("")
async def create_dataset_route(payload: DatasetCreate) -> Dataset:
    obj = DatasetORM(name=payload.name, created_at=datetime.now(timezone.utc))
    await insert_dataset(obj)
    logger.info(
        "dataset.created",
        extra={
            "event": "dataset.created",
            "dataset_id": str(obj.id),
            "name": payload.name,
        },
    )
    return Dataset.model_validate(obj)


@router.get("")
async def get_datasets_route():
    rows = await get_datasets()
    return [
        {"id": d.id, "name": d.name, "created_at": d.created_at.isoformat()}
        for d in rows
    ]


@router.delete("/{dataset_id}")
async def delete_dataset_route(dataset_id: UUID):
    deleted = await delete_dataset(dataset_id)
    if not deleted:
        logger.warning(
            "dataset.route.delete.not_found",
            extra={
                "event": "dataset.route.delete.not_found",
                "dataset_id": str(dataset_id),
            },
        )
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
    logger.info(
        "dataset.deleted",
        extra={"event": "dataset.deleted", "dataset_id": str(dataset_id)},
    )
    return {"deleted": True}


@router.get("/{dataset_id}/documents")
async def get_documents_route(dataset_id: UUID):
    try:
        docs = await get_documents(dataset_id)
    except ValueError as e:
        logger.warning(
            "dataset.route.documents.not_found",
            extra={
                "event": "dataset.route.documents.not_found",
                "dataset_id": str(dataset_id),
                "detail": str(e),
            },
        )
        raise HTTPException(status_code=404, detail=str(e)) from e
    return [
        {
            "id": d.id,
            "name": d.name,
            "url": d.url,
            "blob_url": d.blob_url,
            "dataset_id": d.dataset_id,
        }
        for d in docs
    ]


@router.get("/{dataset_id}/questions")
async def get_questions_route(dataset_id: UUID):
    try:
        questions = await get_questions(dataset_id)
    except ValueError as e:
        logger.warning(
            "dataset.route.questions.not_found",
            extra={
                "event": "dataset.route.questions.not_found",
                "dataset_id": str(dataset_id),
                "detail": str(e),
            },
        )
        raise HTTPException(status_code=404, detail=str(e)) from e
    return [
        {
            "id": q.id,
            "query": q.query,
            "answer": q.answer,
            "document_id": q.document_id,
            "dataset_id": q.dataset_id,
        }
        for q in questions
    ]


@router.post("/{dataset_id}/documents")
async def ingest_document_route(
    dataset_id: UUID,
    file: UploadFile = File(...),
):
    dataset = await get_dataset(dataset_id)
    if dataset is None:
        logger.warning(
            "dataset.route.ingest_documents.dataset_missing",
            extra={
                "event": "dataset.route.ingest_documents.dataset_missing",
                "dataset_id": str(dataset_id),
            },
        )
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    logger.info(
        "dataset.route.ingest_documents.start",
        extra={
            "event": "dataset.route.ingest_documents.start",
            "dataset_id": str(dataset_id),
            "upload_filename": file.filename,
        },
    )
    try:
        docs = await ingest_documents_from_file(file=file, dataset_id=dataset_id)
    except ValueError as e:
        logger.warning(
            "dataset.route.ingest_documents.bad_request",
            extra={
                "event": "dataset.route.ingest_documents.bad_request",
                "dataset_id": str(dataset_id),
                "detail": str(e),
            },
        )
        raise HTTPException(status_code=400, detail=str(e)) from e

    logger.info(
        "dataset.route.ingest_documents.done",
        extra={
            "event": "dataset.route.ingest_documents.done",
            "dataset_id": str(dataset_id),
            "inserted": len(docs),
        },
    )
    return {"inserted": len(docs), "document_ids": [d.id for d in docs]}


@router.post("/{dataset_id}/questions")
async def ingest_dataset_questions_route(
    dataset_id: UUID,
    file: UploadFile = File(...),
):
    dataset = await get_dataset(dataset_id)
    if dataset is None:
        logger.warning(
            "dataset.route.ingest_questions.dataset_missing",
            extra={
                "event": "dataset.route.ingest_questions.dataset_missing",
                "dataset_id": str(dataset_id),
            },
        )
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    logger.info(
        "dataset.route.ingest_questions.start",
        extra={
            "event": "dataset.route.ingest_questions.start",
            "dataset_id": str(dataset_id),
            "upload_filename": file.filename,
        },
    )
    try:
        questions = await ingest_dataset_questions(file=file, dataset_id=dataset_id)
    except DocumentNotFoundError as e:
        logger.warning(
            "dataset.route.ingest_questions.document_missing",
            extra={
                "event": "dataset.route.ingest_questions.document_missing",
                "dataset_id": str(dataset_id),
                "detail": str(e),
            },
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        logger.warning(
            "dataset.route.ingest_questions.bad_request",
            extra={
                "event": "dataset.route.ingest_questions.bad_request",
                "dataset_id": str(dataset_id),
                "detail": str(e),
            },
        )
        raise HTTPException(status_code=400, detail=str(e)) from e

    logger.info(
        "dataset.route.ingest_questions.done",
        extra={
            "event": "dataset.route.ingest_questions.done",
            "dataset_id": str(dataset_id),
            "inserted": len(questions),
        },
    )
    return {"inserted": len(questions), "question_ids": [q.id for q in questions]}

