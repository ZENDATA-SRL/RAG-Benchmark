from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from src.benchmark.repository import get_benchmark
from src.benchmark.service import (
    DocumentNotFoundError,
    ingest_benchmark,
    ingest_document,
)

router = APIRouter(prefix="/benchmark", tags=["benchmark"])


@router.post("/{benchmark_id}/documents")
async def ingest_document_route(
    benchmark_id: UUID,
    file: UploadFile = File(...),
    file_url: str = Form(...),
):
    benchmark = await get_benchmark(benchmark_id)
    if benchmark is None:
        raise HTTPException(
            status_code=404, detail=f"Benchmark {benchmark_id} not found"
        )

    doc = await ingest_document(file=file, file_url=file_url, benchmark_id=benchmark_id)
    return {
        "id": doc.id,
        "name": doc.name,
        "url": doc.url,
        "blob_url": doc.blob_url,
        "benchmark_id": doc.benchmark_id,
    }


@router.post("/{benchmark_id}/questions")
async def ingest_benchmark_route(
    benchmark_id: UUID,
    file: UploadFile = File(...),
):
    benchmark = await get_benchmark(benchmark_id)
    if benchmark is None:
        raise HTTPException(
            status_code=404, detail=f"Benchmark {benchmark_id} not found"
        )

    try:
        questions = await ingest_benchmark(file=file, benchmark_id=benchmark_id)
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {"inserted": len(questions), "question_ids": [q.id for q in questions]}
