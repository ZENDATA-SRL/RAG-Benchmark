# from uuid import UUID

# from config.solver.base import Question
# from core.repository import get_experiment_by_id
# from core.schemas import Answer
# from dataset.repository import get_question
# from evals.repository import insert_benchmark, insert_evaluation
# from src.evals.models import BenchmarkORM as Benchmark
# from src.evals.models import EvaluationORM as Evaluation


# async def compare_answers(answer: Answer, reference: Question) -> float:
#     pass


# async def run_evaluation(experiment_id: UUID) -> Benchmark:
#     benchmark = Benchmark()
#     experiment = await get_experiment_by_id(experiment_id)
#     if experiment is None:
#         raise ValueError(f"Experiment {experiment_id} not found")
#     for answer in experiment.answers:
#         evaluation = Evaluation(
#             benchmark_id=benchmark.id,
#             question_id=answer.question_id,
#             answer_id=answer.id,
#         )
#         question = await get_question(answer.question_id)
#         if question is None:
#             raise ValueError(f"Question {answer.question_id} not found")
#         evaluation.score = await compare_answers(answer, question)
#         await insert_evaluation(evaluation)
#     await insert_benchmark(benchmark)
#     return benchmark
