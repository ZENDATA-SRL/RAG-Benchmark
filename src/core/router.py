import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException

from src.config.schemas import RAGConfigSchema
from src.core.repository import get_answers, get_experiment_by_id
from src.core.service import (
    get_experiments,
    get_question_document_chunk_coverage,
    run_experiment,
    run_process,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/core", tags=["core"])


# here I want the endoint to run sequentially process and experiment
@router.post("")
async def run_process_and_experiment_route(
    dataset_id: UUID, experiment_name: str, rag_config: RAGConfigSchema
):
    logger.info(
        "core.route.process_and_experiment.start",
        extra={
            "event": "core.route.process_and_experiment.start",
            "dataset_id": str(dataset_id),
            "experiment_name": experiment_name,
        },
    )
    try:
        await run_process(rag_config_schema=rag_config, dataset_id=dataset_id)
        await run_experiment(
            rag_config_schema=rag_config,
            dataset_id=dataset_id,
            experiment_name=experiment_name,
        )
    except ValueError as e:
        logger.warning(
            "core.route.process_and_experiment.not_found",
            extra={
                "event": "core.route.process_and_experiment.not_found",
                "dataset_id": str(dataset_id),
                "detail": str(e),
            },
        )
        raise HTTPException(status_code=404, detail=str(e)) from e
    logger.info(
        "core.route.process_and_experiment.done",
        extra={
            "event": "core.route.process_and_experiment.done",
            "dataset_id": str(dataset_id),
            "experiment_name": experiment_name,
        },
    )
    return {"status": "ok"}


@router.post("/process/{dataset_id}")
async def run_process_route(dataset_id: UUID, rag_config: RAGConfigSchema):
    logger.info(
        "core.route.process.start",
        extra={
            "event": "core.route.process.start",
            "dataset_id": str(dataset_id),
        },
    )
    try:
        await run_process(rag_config_schema=rag_config, dataset_id=dataset_id)
    except ValueError as e:
        logger.warning(
            "core.route.process.not_found",
            extra={
                "event": "core.route.process.not_found",
                "dataset_id": str(dataset_id),
                "detail": str(e),
            },
        )
        # Currently raised when dataset does not exist.
        raise HTTPException(status_code=404, detail=str(e)) from e
    logger.info(
        "core.route.process.done",
        extra={"event": "core.route.process.done", "dataset_id": str(dataset_id)},
    )
    return {"status": "ok"}


@router.post("/experiment/{dataset_id}")
async def run_experiment_route(
    dataset_id: UUID, experiment_name: str, rag_config: RAGConfigSchema
):
    logger.info(
        "core.route.experiment.start",
        extra={
            "event": "core.route.experiment.start",
            "dataset_id": str(dataset_id),
            "experiment_name": experiment_name,
        },
    )
    try:
        experiment = await run_experiment(
            rag_config_schema=rag_config,
            dataset_id=dataset_id,
            experiment_name=experiment_name,
        )
    except ValueError as e:
        logger.warning(
            "core.route.experiment.not_found",
            extra={
                "event": "core.route.experiment.not_found",
                "dataset_id": str(dataset_id),
                "detail": str(e),
            },
        )
        raise HTTPException(status_code=404, detail=str(e)) from e
    logger.info(
        "core.route.experiment.done",
        extra={
            "event": "core.route.experiment.done",
            "dataset_id": str(dataset_id),
            "experiment_name": experiment_name,
            "experiment_id": str(experiment.id),
        },
    )
    return experiment


@router.get("/experiment/{experiment_id}")
async def get_experiment_route(experiment_id: UUID):
    try:
        experiment = await get_experiment_by_id(experiment_id)
    except ValueError as e:
        logger.warning(
            "core.route.get_experiment.not_found",
            extra={
                "event": "core.route.get_experiment.not_found",
                "experiment_id": str(experiment_id),
                "detail": str(e),
            },
        )
        raise HTTPException(status_code=404, detail=str(e)) from e
    return experiment


@router.get("/experiment/{experiment_id}/answers")
async def get_answers_route(experiment_id: UUID):
    try:
        answers = await get_answers(experiment_id)
    except ValueError as e:
        logger.warning(
            "core.route.get_answers.not_found",
            extra={
                "event": "core.route.get_answers.not_found",
                "experiment_id": str(experiment_id),
                "detail": str(e),
            },
        )
        raise HTTPException(status_code=404, detail=str(e)) from e
    return answers


@router.get("/experiment/{experiment_id}/question-document-chunk-coverage")
async def get_question_document_chunk_coverage_route(experiment_id: UUID):
    try:
        return await get_question_document_chunk_coverage(experiment_id)
    except ValueError as e:
        logger.warning(
            "core.route.get_question_document_chunk_coverage.not_found",
            extra={
                "event": "core.route.get_question_document_chunk_coverage.not_found",
                "experiment_id": str(experiment_id),
                "detail": str(e),
            },
        )
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/experiments")
async def get_experiments_route():
    try:
        experiments = await get_experiments()
    except ValueError as e:
        logger.warning(
            "core.route.list_experiments.error",
            extra={"event": "core.route.list_experiments.error", "detail": str(e)},
        )
        raise HTTPException(status_code=404, detail=str(e)) from e
    return experiments
