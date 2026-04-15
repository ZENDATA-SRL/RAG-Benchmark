from uuid import UUID

from fastapi import APIRouter, HTTPException

from src.evals.service import fetch_evaluation, get_dataset_evaluations

router = APIRouter(prefix="/evals", tags=["evals"])


@router.get("/fetch/{experiment_id}")
async def fetch_evaluation_route(experiment_id: UUID):
    try:
        return await fetch_evaluation(experiment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{dataset_id}")
async def get_dataset_evaluations_route(dataset_id: UUID):
    try:
        return await get_dataset_evaluations(dataset_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
