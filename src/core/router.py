from uuid import UUID

from fastapi import APIRouter, HTTPException

from src.config.schemas import RAGConfigSchema
from src.core.repository import get_answers, get_experiment_by_id
from src.core.service import get_experiments, run_experiment, run_process

router = APIRouter(prefix="/core", tags=["core"])


# here I want the endoint to run sequentially process and experiment
@router.post("")
async def run_process_and_experiment_route(
    dataset_id: UUID, experiment_name: str, rag_config: RAGConfigSchema
):
    try:
        await run_process(rag_config_schema=rag_config, dataset_id=dataset_id)
        await run_experiment(
            rag_config_schema=rag_config,
            dataset_id=dataset_id,
            experiment_name=experiment_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"status": "ok"}


@router.post("/process/{dataset_id}")
async def run_process_route(dataset_id: UUID, rag_config: RAGConfigSchema):
    try:
        await run_process(rag_config_schema=rag_config, dataset_id=dataset_id)
    except ValueError as e:
        # Currently raised when dataset does not exist.
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"status": "ok"}


@router.post("/experiment/{dataset_id}")
async def run_experiment_route(
    dataset_id: UUID, experiment_name: str, rag_config: RAGConfigSchema
):
    try:
        experiment = await run_experiment(
            rag_config_schema=rag_config,
            dataset_id=dataset_id,
            experiment_name=experiment_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return experiment


@router.get("/experiment/{experiment_id}")
async def get_experiment_route(experiment_id: UUID):
    try:
        experiment = await get_experiment_by_id(experiment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return experiment


@router.get("/experiment/{experiment_id}/answers")
async def get_answers_route(experiment_id: UUID):
    try:
        answers = await get_answers(experiment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return answers


@router.get("/experiments")
async def get_experiments_route():
    try:
        experiments = await get_experiments()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return experiments
