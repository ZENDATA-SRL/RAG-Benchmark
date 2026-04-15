from uuid import UUID

from fastapi import APIRouter, HTTPException

from evals.service import fetch_evaluation


router = APIRouter(prefix="/evals", tags=["evals"])


@router.get("/{experiment_id}")
async def fetch_evaluation_route(experiment_id: UUID):
    try:
        return await fetch_evaluation(experiment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
