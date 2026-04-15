from pydantic import BaseModel

from src.config.schemas import RAGConfig
from src.core.schemas import Answer
from src.dataset.schemas import Dataset


class Score(BaseModel):
    score: float
    name: str


class AnswerWithScores(BaseModel):
    answer: Answer
    scores: list[Score]


class ExperimentWithRagConfig(BaseModel):
    ragconfig: RAGConfig
    name: str
    answers_with_scores: list[AnswerWithScores]


class Evaluation(BaseModel):
    dataset: Dataset
    experiments: list[ExperimentWithRagConfig]
