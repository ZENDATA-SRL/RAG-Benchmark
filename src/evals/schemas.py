from pydantic import BaseModel

from config.schemas import RAGConfig
from core.schemas import Answer
from dataset.schemas import Dataset


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
