from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core.pagination import Page
from src.infrastructure.database.enums import EvidenceLinkStatus, RelevanceGrade
from src.pipelines.schemas import DeduplicatedRead

# State of the evidence of a question under one chunking configuration, as read: the
# stored link status, or `not_reviewed` when there is no link at all.
EvidenceStatus = Literal["not_reviewed", "to_review", "confirmed", "not_found"]


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
    """A question with its gold documents and expected answers.

    `frozen` is true when a snapshot holds the question: it can then only be replaced.
    `evidence_status` is set when the listing was asked for a chunking configuration.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    qa_set_id: uuid.UUID
    text: str
    tags: list[str]
    answerable: bool
    gold_documents: list[GoldDocumentRead]
    expected_answers: list[ExpectedAnswerRead]
    frozen: bool = False
    replaced_by_question_id: uuid.UUID | None = None
    evidence_status: EvidenceStatus | None = None


class ExpectedAnswerWrite(BaseModel):
    """An acceptable answer; with none marked primary, the first one is."""

    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=10000)
    is_primary: bool = False


def _clean_tags(tags: list[str]) -> list[str]:
    return list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))


def _single_primary(answers: list[ExpectedAnswerWrite]) -> list[ExpectedAnswerWrite]:
    if sum(answer.is_primary for answer in answers) > 1:
        raise ValueError("at most one expected answer can be primary")
    return answers


class QuestionCreate(BaseModel):
    """A question written in the UI; gold documents can also come later, from evidence."""

    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=5000)
    tags: list[str] = Field(default_factory=list)
    answerable: bool = True
    expected_answers: list[ExpectedAnswerWrite] = Field(default_factory=list)
    gold_document_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def _tags(cls, tags: list[str]) -> list[str]:
        return _clean_tags(tags)

    @field_validator("expected_answers")
    @classmethod
    def _answers(cls, answers: list[ExpectedAnswerWrite]) -> list[ExpectedAnswerWrite]:
        return _single_primary(answers)

    @field_validator("gold_document_ids")
    @classmethod
    def _documents(cls, ids: list[uuid.UUID]) -> list[uuid.UUID]:
        return list(dict.fromkeys(ids))


class QuestionUpdate(BaseModel):
    """Changes to a question not frozen yet; an omitted field is left as it is.

    `expected_answers`, when given, replaces the whole list.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    text: str | None = Field(default=None, min_length=1, max_length=5000)
    tags: list[str] | None = None
    answerable: bool | None = None
    expected_answers: list[ExpectedAnswerWrite] | None = None

    @field_validator("tags")
    @classmethod
    def _tags(cls, tags: list[str] | None) -> list[str] | None:
        return None if tags is None else _clean_tags(tags)

    @field_validator("expected_answers")
    @classmethod
    def _answers(
        cls, answers: list[ExpectedAnswerWrite] | None
    ) -> list[ExpectedAnswerWrite] | None:
        return None if answers is None else _single_primary(answers)


class GoldDocumentsWrite(BaseModel):
    """The complete list of gold documents of a question."""

    document_ids: list[uuid.UUID]

    @field_validator("document_ids")
    @classmethod
    def _documents(cls, ids: list[uuid.UUID]) -> list[uuid.UUID]:
        return list(dict.fromkeys(ids))


class EvidenceChunkWrite(BaseModel):
    """A chunk chosen as evidence, sufficient on its own or supporting the answer."""

    chunk_id: uuid.UUID
    relevance: RelevanceGrade
    graded_relevance: int | None = Field(
        default=None, ge=0, le=3, description="Optional graded relevance, 0 to 3."
    )


class EvidenceWrite(BaseModel):
    """The whole evidence of a question under one chunking configuration.

    `to_review` saves a draft; `confirmed` needs chunks; `not_found` takes none. Both
    decisions need `annotator`.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    chunking_configuration_id: uuid.UUID
    status: EvidenceLinkStatus
    chunks: list[EvidenceChunkWrite] = Field(default_factory=list)
    annotator: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _distinct_chunks(self) -> EvidenceWrite:
        ids = [chunk.chunk_id for chunk in self.chunks]
        if len(ids) != len(set(ids)):
            raise ValueError("a chunk can appear only once in the evidence")
        return self


class EvidenceChunkRead(BaseModel):
    """An evidence chunk with where it comes from, for the review panel."""

    model_config = ConfigDict(from_attributes=True)

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    ordinal: int
    text: str
    metadata: dict[str, Any]
    relevance: RelevanceGrade
    graded_relevance: int | None = None


class EvidenceRead(BaseModel):
    """The evidence of a question under one chunking configuration.

    `added_gold_document_ids` lists the documents a confirmation added to the gold.
    """

    model_config = ConfigDict(from_attributes=True)

    question_id: uuid.UUID
    chunking_configuration_id: uuid.UUID
    status: EvidenceStatus
    confirmed_by: str | None = None
    confirmed_at: dt.datetime | None = None
    chunks: list[EvidenceChunkRead]
    added_gold_document_ids: list[uuid.UUID] = Field(default_factory=list)


class EvidenceCoverageRead(BaseModel):
    """How far the evidence of a set is reviewed under one configuration."""

    model_config = ConfigDict(from_attributes=True)

    qa_set_id: uuid.UUID
    chunking_configuration_id: uuid.UUID
    answerable: int
    not_answerable: int
    confirmed: int
    not_found: int
    to_review: int
    not_reviewed: int


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
