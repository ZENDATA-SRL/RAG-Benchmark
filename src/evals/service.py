import asyncio
import logging
import time
from uuid import UUID

from langfuse.api import DatasetRunWithItems

from src.core.repository import (
    get_answer_by_question_and_experiment_id,
    get_experiment_by_id,
    get_experiments_by_dataset_id,
)
from src.dataset.repository import get_dataset
from src.dataset.schemas import Dataset
from src.evals.models import ScoreORM, TraceORM
from src.evals.repository import (
    create_evaluator,
    get_evaluator_by_name,
    get_score_by_trace_id_and_evaluator_id,
    get_scores_by_trace_id,
    get_trace_by_langfuse_trace_id,
    insert_score,
    insert_trace,
)
from src.evals.schemas import (
    AnswerWithScores,
    Evaluation,
    ExperimentWithRagConfig,
    Score,
)
from src.infrastructure.langfuse_client import get_langfuse_client

logger = logging.getLogger(__name__)


async def fetch_evaluation(experiment_id: UUID):
    t0 = time.perf_counter()
    logger.debug(
        "evals.fetch_evaluation.start",
        extra={
            "event": "evals.fetch_evaluation.start",
            "experiment_id": str(experiment_id),
        },
    )
    experiment = await get_experiment_by_id(experiment_id)
    if experiment is None:
        logger.warning(
            "evals.fetch_evaluation.not_found",
            extra={
                "event": "evals.fetch_evaluation.not_found",
                "experiment_id": str(experiment_id),
            },
        )
        raise ValueError(f"Experiment {experiment_id} not found")
    dataset = await get_dataset(experiment.dataset_id)
    if dataset is None:
        logger.warning(
            "evals.fetch_evaluation.dataset_not_found",
            extra={
                "event": "evals.fetch_evaluation.dataset_not_found",
                "experiment_id": str(experiment_id),
                "dataset_id": str(experiment.dataset_id),
            },
        )
        raise ValueError(f"Dataset {experiment.dataset_id} not found")

    langfuse_client = get_langfuse_client()
    try:
        t_run = time.perf_counter()
        run: DatasetRunWithItems = langfuse_client.get_dataset_run(
            dataset_name=dataset.name, run_name=experiment.name
        )
        run_ms = round((time.perf_counter() - t_run) * 1000, 2)
        if run is None:
            logger.warning(
                "evals.fetch_evaluation.run_not_found",
                extra={
                    "event": "evals.fetch_evaluation.run_not_found",
                    "experiment_id": str(experiment_id),
                    "dataset_name": dataset.name,
                    "run_name": experiment.name,
                    "dataset_run_id": str(experiment.dataset_run_id)
                    if getattr(experiment, "dataset_run_id", None)
                    else None,
                    "duration_ms": run_ms,
                },
            )
            raise ValueError(f"Run {experiment.dataset_run_id} not found")

        item_count = len(run.dataset_run_items or [])
        logger.debug(
            "evals.fetch_evaluation.run_loaded",
            extra={
                "event": "evals.fetch_evaluation.run_loaded",
                "experiment_id": str(experiment_id),
                "dataset_name": dataset.name,
                "run_name": experiment.name,
                "run_item_count": item_count,
                "duration_ms": run_ms,
            },
        )

        inserted_trace_count = 0
        inserted_score_count = 0

        for run_item in run.dataset_run_items:
            t_item = time.perf_counter()

            trace = await langfuse_client.async_api.trace.get(
                trace_id=run_item.trace_id
            )
            if trace is None:
                logger.warning(
                    "evals.fetch_evaluation.trace_not_found",
                    extra={
                        "event": "evals.fetch_evaluation.trace_not_found",
                        "experiment_id": str(experiment_id),
                        "langfuse_trace_id": str(run_item.trace_id),
                    },
                )
                raise ValueError(f"Trace {run_item.trace_id} not found")

            dataset_item = await langfuse_client.async_api.dataset_items.get(
                run_item.dataset_item_id
            )
            question_id = dataset_item.metadata["id"]
            answer = await get_answer_by_question_and_experiment_id(
                question_id=question_id, experiment_id=experiment_id
            )
            if answer is None:
                logger.warning(
                    "evals.fetch_evaluation.answer_not_found",
                    extra={
                        "event": "evals.fetch_evaluation.answer_not_found",
                        "experiment_id": str(experiment_id),
                        "question_id": str(question_id),
                        "dataset_item_id": str(run_item.dataset_item_id),
                    },
                )
                raise ValueError(f"Answer {question_id} not found")

            trace_obj = await get_trace_by_langfuse_trace_id(run_item.trace_id)
            if trace_obj is None:
                trace_obj = await insert_trace(
                    TraceORM(answer_id=answer.id, langfuse_trace_id=run_item.trace_id)
                )
            inserted_trace_count += 1

            scores = trace.scores or []
            for score in scores:
                evaluator = await get_evaluator_by_name(score.name)
                if evaluator is None:
                    evaluator = await create_evaluator(score.name)
                score_obj = await get_score_by_trace_id_and_evaluator_id(
                    trace_obj.id, evaluator.id
                )
                if score_obj is None:
                    score_obj = await insert_score(
                        ScoreORM(
                            trace_id=trace_obj.id,
                            evaluator_id=evaluator.id,
                            score=score.value,
                        )
                    )
                    inserted_score_count += 1

            item_ms = round((time.perf_counter() - t_item) * 1000, 2)
            logger.debug(
                "evals.fetch_evaluation.item_complete",
                extra={
                    "event": "evals.fetch_evaluation.item_complete",
                    "experiment_id": str(experiment_id),
                    "dataset_item_id": str(run_item.dataset_item_id),
                    "question_id": str(question_id),
                    "answer_id": str(answer.id),
                    "trace_id": str(trace_obj.id),
                    "langfuse_trace_id": str(run_item.trace_id),
                    "score_count": len(scores),
                    "duration_ms": item_ms,
                },
            )

        total_ms = round((time.perf_counter() - t0) * 1000, 2)
        logger.info(
            "evals.fetch_evaluation.complete",
            extra={
                "event": "evals.fetch_evaluation.complete",
                "experiment_id": str(experiment_id),
                "dataset_id": str(experiment.dataset_id),
                "dataset_name": dataset.name,
                "run_name": experiment.name,
                "run_item_count": item_count,
                "inserted_trace_count": inserted_trace_count,
                "inserted_score_count": inserted_score_count,
                "duration_ms": total_ms,
            },
        )
    except Exception:
        logger.exception(
            "evals.fetch_evaluation.failed",
            extra={
                "event": "evals.fetch_evaluation.failed",
                "experiment_id": str(experiment_id),
            },
        )
        raise


async def get_dataset_evaluations(dataset_id: UUID) -> Evaluation:
    t0 = time.perf_counter()
    logger.debug(
        "evals.get_dataset_evaluations.start",
        extra={
            "event": "evals.get_dataset_evaluations.start",
            "dataset_id": str(dataset_id),
        },
    )
    experiments = await get_experiments_by_dataset_id(dataset_id)
    tasks = [fetch_evaluation(experiment.id) for experiment in experiments]
    await asyncio.gather(*tasks)
    dataset = await get_dataset(dataset_id)
    if dataset is None:
        logger.warning(
            "evals.get_dataset_evaluations.dataset_not_found",
            extra={
                "event": "evals.get_dataset_evaluations.dataset_not_found",
                "dataset_id": str(dataset_id),
            },
        )
        raise ValueError(f"Dataset {dataset_id} not found")
    evaluations = []
    for experiment in experiments:
        experiment_with_rag_config = ExperimentWithRagConfig(
            ragconfig=experiment.rag_config,
            name=experiment.name,
            answers_with_scores=[
                AnswerWithScores(
                    answer=answer,
                    scores=[
                        Score(score=score.score, name=score.evaluator.name)
                        for score in (
                            await get_scores_by_trace_id(answer.trace.id)
                            if answer.trace is not None
                            else []
                        )
                    ],
                )
                for answer in experiment.answers
            ],
        )
        evaluations.append(experiment_with_rag_config)
    total_ms = round((time.perf_counter() - t0) * 1000, 2)
    logger.info(
        "evals.get_dataset_evaluations.complete",
        extra={
            "event": "evals.get_dataset_evaluations.complete",
            "dataset_id": str(dataset_id),
            "dataset_name": dataset.name,
            "experiment_count": len(experiments),
            "duration_ms": total_ms,
        },
    )
    return Evaluation(
        dataset=Dataset(
            id=dataset.id,
            name=dataset.name,
            created_at=dataset.created_at,
        ),
        experiments=evaluations,
    )
