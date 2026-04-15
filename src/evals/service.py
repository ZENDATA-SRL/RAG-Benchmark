from uuid import UUID

from langfuse.api import DatasetRunWithItems

from core.repository import (
    get_answer_by_question_and_experiment_id,
    get_experiment_by_id,
    get_experiments_by_dataset_id,
)
from dataset.repository import get_dataset
from dataset.schemas import Dataset
from evals.models import ScoreORM, TraceORM
from evals.repository import (
    create_evaluator,
    get_evaluator_by_name,
    get_scores_by_trace_id,
    insert_score,
    insert_trace,
)
from evals.schemas import AnswerWithScores, Evaluation, ExperimentWithRagConfig, Score
from infrastructure.langfuse_client import get_langfuse_client


async def fetch_evaluation(experiment_id: UUID):
    experiment = await get_experiment_by_id(experiment_id)
    if experiment.answers[0].trace is not None:
        return None
    dataset = await get_dataset(experiment.dataset_id)

    langfuse_client = get_langfuse_client()
    run: DatasetRunWithItems = await langfuse_client.get_dataset_run(
        dataset_name=dataset.name, run_name=experiment.name
    )
    if run is None:
        raise ValueError(f"Run {experiment.dataset_run_id} not found")
    for run_item in run.dataset_run_items:
        trace = await langfuse_client.async_api.trace.get(trace_id=run_item.trace_id)
        if trace is None:
            raise ValueError(f"Trace {run_item.trace_id} not found")
        dataset_item = await langfuse_client.async_api.dataset_items.get(run_item.id)
        question_id = dataset_item.metadata["question_id"]
        answer = await get_answer_by_question_and_experiment_id(
            question_id, experiment_id
        )
        if answer is None:
            raise ValueError(f"Answer {question_id} not found")

        trace_obj = await insert_trace(
            TraceORM(answer_id=answer.id, langfuse_trace_id=run_item.trace_id)
        )
        scores = trace.scores
        for score in scores:
            evaluator = await get_evaluator_by_name(score.name)
            if evaluator is None:
                evaluator = await create_evaluator(score.name)
            await insert_score(
                ScoreORM(
                    trace_id=trace_obj.id, evaluator_id=evaluator.id, score=score.value
                )
            )


async def get_evaluations_by_dataset_id(dataset_id: UUID) -> Evaluation:
    experiments = await get_experiments_by_dataset_id(dataset_id)
    dataset = await get_dataset(dataset_id)
    evaluations = []
    for experiment in experiments:
        await fetch_evaluation(experiment.id)
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
    return Evaluation(
        dataset=Dataset(
            id=dataset.id,
            name=dataset.name,
            created_at=dataset.created_at,
        ),
        experiments=evaluations,
    )
