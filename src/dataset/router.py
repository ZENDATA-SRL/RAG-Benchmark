from uuid import UUID

from datetime import datetime, timezone

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
    ingest_documents_from_xlsx,
)

router = APIRouter(prefix="/dataset", tags=["dataset"])


@router.post("")
async def create_dataset_route(payload: DatasetCreate) -> Dataset:
    obj = DatasetORM(name=payload.name, created_at=datetime.now(timezone.utc))
    await insert_dataset(obj)
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
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
    return {"deleted": True}


@router.get("/{dataset_id}/documents")
async def get_documents_route(dataset_id: UUID):
    try:
        docs = await get_documents(dataset_id)
    except ValueError as e:
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
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    try:
        docs = await ingest_documents_from_xlsx(file=file, dataset_id=dataset_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {"inserted": len(docs), "document_ids": [d.id for d in docs]}


@router.post("/{dataset_id}/questions")
async def ingest_dataset_questions_route(
    dataset_id: UUID,
    file: UploadFile = File(...),
):
    dataset = await get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    try:
        questions = await ingest_dataset_questions(file=file, dataset_id=dataset_id)
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {"inserted": len(questions), "question_ids": [q.id for q in questions]}

