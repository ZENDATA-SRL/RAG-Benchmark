from __future__ import annotations

import dataclasses
import datetime as dt
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.enums import EvidenceLinkStatus, RelevanceGrade
from src.qa_sets.exceptions import (
    DocumentsOutsideCorpusError,
    EvidenceChunksOutsideConfigurationError,
    InvalidEvidenceError,
)
from src.qa_sets.repository import EvidenceRepository, QuestionRepository
from src.qa_sets.service import NOT_REVIEWED, QASetService, QuestionService


@dataclasses.dataclass(frozen=True)
class EvidenceChunkInput:
    chunk_id: uuid.UUID
    relevance: RelevanceGrade
    graded_relevance: int | None = None


@dataclasses.dataclass(frozen=True)
class EvidenceChunkView:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    ordinal: int
    text: str
    metadata: dict[str, Any]
    relevance: RelevanceGrade
    graded_relevance: int | None


@dataclasses.dataclass(frozen=True)
class EvidenceView:
    """The evidence of a question under one chunking configuration.

    `status` is `not_reviewed` when no link exists, which is different from `not_found`:
    the first means nobody looked, the second that the evidence is not in these chunks.
    """

    question_id: uuid.UUID
    chunking_configuration_id: uuid.UUID
    status: str
    confirmed_by: str | None
    confirmed_at: dt.datetime | None
    chunks: list[EvidenceChunkView]
    added_gold_document_ids: list[uuid.UUID] = dataclasses.field(default_factory=list)


class EvidenceService:
    """Which chunks hold the answer to a question, reviewed by a person per configuration.

    The link is anchored to a chunking configuration, the only thing whose change costs
    human work: it stays valid when the corpus grows or the embedder changes. Nothing
    becomes evidence without a person's decision, recorded with their name.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.qa_sets = QASetService(session)
        self.questions = QuestionService(session)
        self.question_rows = QuestionRepository(session)
        self.links = EvidenceRepository(session)

    async def get(
        self, question_id: uuid.UUID, chunking_configuration_id: uuid.UUID
    ) -> EvidenceView:
        """Return the evidence of a question under a configuration.

        Raises:
            QuestionNotFoundError: If the question does not exist.
            ChunkingConfigurationNotFoundError: If the configuration does not exist.
        """
        await self.questions.get(question_id)
        await self.qa_sets.require_configuration(chunking_configuration_id)
        return await self._view(question_id, chunking_configuration_id)

    async def put(
        self,
        question_id: uuid.UUID,
        chunking_configuration_id: uuid.UUID,
        *,
        status: EvidenceLinkStatus,
        chunks: list[EvidenceChunkInput],
        annotator: str | None,
    ) -> EvidenceView:
        """Write the whole evidence of a question under a configuration.

        Replaces the link and its chunks, so saving the same decision twice changes
        nothing. `to_review` keeps a partial selection as a draft; `confirmed` needs at
        least one chunk; `not_found` records that the evidence is not in these chunks and
        takes none. Both decisions need the name of the person who took them. Confirming
        adds the documents of the chunks to the gold documents of the question, which is
        how authoring from chunks yields the document-level gold too.

        Raises:
            QuestionNotFoundError: If the question does not exist.
            ChunkingConfigurationNotFoundError: If the configuration does not exist.
            InvalidEvidenceError: If the status rules are broken or the question is not
                answerable.
            EvidenceChunksOutsideConfigurationError: If a chunk is not a chunk of the
                configuration.
            DocumentsOutsideCorpusError: If a chunk's document is not in the origin
                corpus of the set.
        """
        question = await self.questions.get(question_id)
        qa_set = await self.qa_sets.get(question.qa_set_id)
        await self.qa_sets.require_configuration(chunking_configuration_id)
        _check_rules(question.answerable, status, chunks, annotator)

        chunk_documents = await self.links.chunk_documents(
            [chunk.chunk_id for chunk in chunks], chunking_configuration_id
        )
        outside = [c.chunk_id for c in chunks if c.chunk_id not in chunk_documents]
        if outside:
            raise EvidenceChunksOutsideConfigurationError(
                chunking_configuration_id, outside
            )
        documents = sorted(set(chunk_documents.values()))
        if qa_set.origin_corpus_id is not None:
            in_corpus = await self.question_rows.existing_documents(
                documents, qa_set.origin_corpus_id
            )
            missing = [d for d in documents if d not in in_corpus]
            if missing:
                raise DocumentsOutsideCorpusError(missing)

        decided = status is not EvidenceLinkStatus.TO_REVIEW
        link_id = await self.links.upsert(
            question.id,
            chunking_configuration_id,
            status=status,
            confirmed_by=annotator.strip() if decided and annotator else None,
            confirmed_at=dt.datetime.now(dt.UTC) if decided else None,
        )
        await self.links.replace_chunks(
            link_id,
            [
                {
                    "chunk_id": chunk.chunk_id,
                    "relevance": chunk.relevance,
                    "graded_relevance": chunk.graded_relevance,
                }
                for chunk in chunks
            ],
        )

        added: list[uuid.UUID] = []
        if status is EvidenceLinkStatus.CONFIRMED:
            current = await self.question_rows.gold_document_ids(question.id)
            added = [d for d in documents if d not in current]
            await self.question_rows.add_gold_documents(question.id, added)
        await self.session.flush()
        view = await self._view(question.id, chunking_configuration_id)
        return dataclasses.replace(view, added_gold_document_ids=added)

    async def _view(
        self, question_id: uuid.UUID, chunking_configuration_id: uuid.UUID
    ) -> EvidenceView:
        link = await self.links.get(question_id, chunking_configuration_id)
        if link is None:
            return EvidenceView(
                question_id=question_id,
                chunking_configuration_id=chunking_configuration_id,
                status=NOT_REVIEWED,
                confirmed_by=None,
                confirmed_at=None,
                chunks=[],
            )
        rows = await self.links.chunks_of_link(link.id)
        return EvidenceView(
            question_id=question_id,
            chunking_configuration_id=chunking_configuration_id,
            status=link.status.value,
            confirmed_by=link.confirmed_by,
            confirmed_at=link.confirmed_at,
            chunks=[
                EvidenceChunkView(
                    chunk_id=chunk.id,
                    document_id=document_id,
                    filename=filename,
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                    metadata=chunk.chunk_metadata or {},
                    relevance=link_chunk.relevance,
                    graded_relevance=link_chunk.graded_relevance,
                )
                for link_chunk, chunk, document_id, filename in rows
            ],
        )


def _check_rules(
    answerable: bool,
    status: EvidenceLinkStatus,
    chunks: list[EvidenceChunkInput],
    annotator: str | None,
) -> None:
    if not answerable:
        raise InvalidEvidenceError(
            "question_not_answerable",
            "the question is flagged as not answerable, so it has no evidence to review",
        )
    if status is EvidenceLinkStatus.CONFIRMED and not chunks:
        raise InvalidEvidenceError(
            "chunks_required", "confirmed evidence needs at least one chunk"
        )
    if status is EvidenceLinkStatus.NOT_FOUND and chunks:
        raise InvalidEvidenceError(
            "chunks_not_allowed",
            "evidence that was not found cannot list chunks; save a draft instead",
        )
    if status is not EvidenceLinkStatus.TO_REVIEW and not (annotator or "").strip():
        raise InvalidEvidenceError(
            "annotator_required",
            "a decision on the evidence needs the annotator's name",
        )
