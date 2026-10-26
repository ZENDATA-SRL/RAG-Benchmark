from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from src.core.pagination import Page
from src.pipelines.schemas import DeduplicatedRead


class QASetCreate(BaseModel):
    """Payload creating a QA set."""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    origin_corpus_id: uuid.UUID | None = Field(
        default=None,
        description="Corpus the gold file names of an import are resolved in.",
    )


class QASetRead(BaseModel):
    """A QA set as exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    origin_corpus_id: uuid.UUID | None = None
    question_count: int = 0
    created_at: dt.datetime
    updated_at: dt.datetime


class GoldDocumentRead(BaseModel):
    """A document that contains the answer to a question."""

    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    filename: str


class ExpectedAnswerRead(BaseModel):
    """An acceptable answer to a question; the primary one comes first."""

    model_config = ConfigDict(from_attributes=True)

    text: str
    is_primary: bool


class QuestionRead(BaseModel):
    """A question with its gold documents and expected answers."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str
    tags: list[str]
    answerable: bool
    gold_documents: list[GoldDocumentRead]
    expected_answers: list[ExpectedAnswerRead]


class QASetDetail(QASetRead):
    """A QA set with one page of its questions."""

    questions: Page[QuestionRead]


class ImportedQuestionRead(BaseModel):
    """A row turned into a question."""

    model_config = ConfigDict(from_attributes=True)

    row: int
    question_id: uuid.UUID
    text: str
    gold_documents: list[GoldDocumentRead]


class UnresolvedRowRead(BaseModel):
    """A row whose gold files match no document of the corpus."""

    model_config = ConfigDict(from_attributes=True)

    row: int
    question: str
    files: list[str]


class AmbiguousCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    filename: str
    content_hash: str


class AmbiguousFileRead(BaseModel):
    """A gold file name shared by several documents; the row can name one by hash."""

    model_config = ConfigDict(from_attributes=True)

    file: str
    candidates: list[AmbiguousCandidateRead]


class AmbiguousRowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row: int
    question: str
    files: list[AmbiguousFileRead]


class InvalidRowRead(BaseModel):
    """A malformed row, e.g. an empty question or an answerable one without gold files."""

    model_config = ConfigDict(from_attributes=True)

    row: int
    question: str
    reason: str


class ImportSummaryRead(BaseModel):
    """What an import did, row by row: nothing is dropped without being listed.

    `existing` are rows whose question text was already in the set: questions are
    immutable, so a re-import leaves them as they are instead of duplicating them.
    """

    model_config = ConfigDict(from_attributes=True)

    qa_set_id: uuid.UUID
    total_rows: int
    imported: list[ImportedQuestionRead]
    existing: list[ImportedQuestionRead]
    unresolved: list[UnresolvedRowRead]
    ambiguous: list[AmbiguousRowRead]
    invalid: list[InvalidRowRead]


class QASetSnapshotCreate(BaseModel):
    """Payload freezing the current questions of a set."""

    label: str | None = Field(default=None, min_length=1, max_length=200)


class QASetSnapshotRead(BaseModel):
    """An immutable freeze of a QA set."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    qa_set_id: uuid.UUID
    label: str
    question_count: int
    composition_hash: str
    frozen_at: dt.datetime


class QASetSnapshotCreated(DeduplicatedRead):
    """A snapshot with the outcome of the get-or-create that returned it."""

    snapshot: QASetSnapshotRead
