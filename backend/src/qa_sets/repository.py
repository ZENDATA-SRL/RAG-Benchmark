from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.artifacts.models import Chunk, ChunkResult
from src.corpora.models import CorpusDocument
from src.documents.models import Document
from src.infrastructure.database.enums import EvidenceLinkStatus
from src.qa_sets.models import (
    EvidenceLink,
    EvidenceLinkChunk,
    ExpectedAnswer,
    GoldDocument,
    QASet,
    QASetSnapshot,
    QASnapshotQuestion,
    Question,
)


def _active():
    """Questions still in their set: a replaced question only lives on in snapshots."""
    return Question.replaced_by_question_id.is_(None)


class QASetRepository:
    """Data access for `qa_sets`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, qa_set: QASet) -> QASet:
        self.session.add(qa_set)
        return qa_set

    async def get_by_id(self, qa_set_id: uuid.UUID) -> QASet | None:
        return await self.session.get(QASet, qa_set_id)

    async def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[QASet]:
        stmt = (
            select(QASet)
            .order_by(QASet.created_at.desc(), QASet.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return (await self.session.scalars(stmt)).all()

    async def count(self) -> int:
        return await self.session.scalar(select(func.count()).select_from(QASet)) or 0

    async def question_counts(
        self, qa_set_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """Number of questions of each set, for the sets that have any."""
        if not qa_set_ids:
            return {}
        stmt = (
            select(Question.qa_set_id, func.count())
            .where(Question.qa_set_id.in_(qa_set_ids), _active())
            .group_by(Question.qa_set_id)
        )
        return {
            set_id: count for set_id, count in (await self.session.execute(stmt)).all()
        }


class QuestionRepository:
    """Data access for `questions`, their gold documents and expected answers."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, question: Question) -> Question:
        self.session.add(question)
        return question

    async def get_by_id(self, question_id: uuid.UUID) -> Question | None:
        return await self.session.get(Question, question_id)

    async def delete(self, question: Question) -> None:
        await self.session.delete(question)

    async def frozen_ids(self, question_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        """The questions, among these, that at least one snapshot holds."""
        if not question_ids:
            return set()
        stmt = (
            select(QASnapshotQuestion.question_id)
            .where(QASnapshotQuestion.question_id.in_(question_ids))
            .distinct()
        )
        return set((await self.session.scalars(stmt)).all())

    async def active_with_text(
        self, qa_set_id: uuid.UUID, text: str
    ) -> uuid.UUID | None:
        stmt = select(Question.id).where(
            Question.qa_set_id == qa_set_id, Question.text == text, _active()
        )
        return await self.session.scalar(stmt.limit(1))

    async def replace_expected_answers(
        self, question_id: uuid.UUID, answers: Sequence[ExpectedAnswer]
    ) -> None:
        await self.session.execute(
            delete(ExpectedAnswer).where(ExpectedAnswer.question_id == question_id)
        )
        self.session.add_all(answers)

    async def gold_document_ids(self, question_id: uuid.UUID) -> set[uuid.UUID]:
        stmt = select(GoldDocument.document_id).where(
            GoldDocument.question_id == question_id
        )
        return set((await self.session.scalars(stmt)).all())

    async def remove_gold_documents(
        self, question_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
    ) -> None:
        if not document_ids:
            return
        await self.session.execute(
            delete(GoldDocument).where(
                GoldDocument.question_id == question_id,
                GoldDocument.document_id.in_(document_ids),
            )
        )

    async def existing_documents(
        self, document_ids: Sequence[uuid.UUID], corpus_id: uuid.UUID | None
    ) -> set[uuid.UUID]:
        """The documents, among these, that exist, and are in the corpus when one is given."""
        if not document_ids:
            return set()
        stmt = select(Document.id).where(Document.id.in_(document_ids))
        if corpus_id is not None:
            stmt = stmt.join(
                CorpusDocument, CorpusDocument.document_id == Document.id
            ).where(CorpusDocument.corpus_id == corpus_id)
        return set((await self.session.scalars(stmt)).all())

    async def add_gold_documents(
        self, question_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
    ) -> None:
        if not document_ids:
            return
        await self.session.execute(
            pg_insert(GoldDocument)
            .values(
                [
                    {"question_id": question_id, "document_id": document_id}
                    for document_id in document_ids
                ]
            )
            .on_conflict_do_nothing()
        )

    def add_expected_answer(self, answer: ExpectedAnswer) -> ExpectedAnswer:
        self.session.add(answer)
        return answer

    async def answers_by_question(
        self, question_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[ExpectedAnswer]]:
        """Expected answers of each question, the primary one first."""
        if not question_ids:
            return {}
        stmt = (
            select(ExpectedAnswer)
            .where(ExpectedAnswer.question_id.in_(question_ids))
            .order_by(
                ExpectedAnswer.is_primary.desc(),
                ExpectedAnswer.created_at,
                ExpectedAnswer.id,
            )
        )
        answers: dict[uuid.UUID, list[ExpectedAnswer]] = {}
        for answer in (await self.session.scalars(stmt)).all():
            answers.setdefault(answer.question_id, []).append(answer)
        return answers

    async def texts_in_set(self, qa_set_id: uuid.UUID) -> dict[str, uuid.UUID]:
        """Question text -> id for a set: the key a re-import is deduplicated on."""
        stmt = select(Question.text, Question.id).where(
            Question.qa_set_id == qa_set_id, _active()
        )
        return {
            text: question_id
            for text, question_id in (await self.session.execute(stmt)).all()
        }

    async def list_by_set(
        self, qa_set_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> Sequence[Question]:
        stmt = (
            select(Question)
            .where(Question.qa_set_id == qa_set_id, _active())
            .order_by(Question.created_at, Question.id)
            .limit(limit)
            .offset(offset)
        )
        return (await self.session.scalars(stmt)).all()

    async def count_by_set(self, qa_set_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Question)
            .where(Question.qa_set_id == qa_set_id, _active())
        )
        return await self.session.scalar(stmt) or 0

    async def list_by_ids(
        self, question_ids: Sequence[uuid.UUID]
    ) -> Sequence[Question]:
        if not question_ids:
            return []
        stmt = (
            select(Question)
            .where(Question.id.in_(question_ids))
            .order_by(Question.created_at, Question.id)
        )
        return (await self.session.scalars(stmt)).all()

    async def ids_by_set(self, qa_set_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(Question.id).where(Question.qa_set_id == qa_set_id, _active())
        return list((await self.session.scalars(stmt)).all())

    async def answerable_ids_by_set(self, qa_set_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(Question.id).where(
            Question.qa_set_id == qa_set_id, Question.answerable, _active()
        )
        return list((await self.session.scalars(stmt)).all())

    async def gold_files_by_question(
        self, question_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[tuple[str, str]]]:
        """Gold documents `(filename, content_hash)` of each question, ordered by name."""
        if not question_ids:
            return {}
        stmt = (
            select(GoldDocument.question_id, Document.filename, Document.content_hash)
            .join(Document, Document.id == GoldDocument.document_id)
            .where(GoldDocument.question_id.in_(question_ids))
            .order_by(Document.filename, Document.id)
        )
        files: dict[uuid.UUID, list[tuple[str, str]]] = {}
        for question_id, filename, content_hash in (
            await self.session.execute(stmt)
        ).all():
            files.setdefault(question_id, []).append((filename, content_hash))
        return files

    async def ambiguous_filenames(
        self, filenames: Sequence[str], corpus_id: uuid.UUID | None
    ) -> set[str]:
        """The names, among these, that more than one document carries.

        Scoped like the resolution of an import: the corpus when one is given, every
        document otherwise. These are the names a re-import could not resolve.
        """
        if not filenames:
            return set()
        stmt = (
            select(Document.filename)
            .where(Document.filename.in_(filenames))
            .group_by(Document.filename)
            .having(func.count(func.distinct(Document.id)) > 1)
        )
        if corpus_id is not None:
            stmt = stmt.join(
                CorpusDocument, CorpusDocument.document_id == Document.id
            ).where(CorpusDocument.corpus_id == corpus_id)
        return set((await self.session.scalars(stmt)).all())

    async def gold_by_question(
        self, question_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[tuple[uuid.UUID, str]]]:
        """Gold documents `(id, filename)` of each question, ordered by file name."""
        if not question_ids:
            return {}
        stmt = (
            select(GoldDocument.question_id, Document.id, Document.filename)
            .join(Document, Document.id == GoldDocument.document_id)
            .where(GoldDocument.question_id.in_(question_ids))
            .order_by(Document.filename, Document.id)
        )
        gold: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = {}
        for question_id, document_id, filename in (
            await self.session.execute(stmt)
        ).all():
            gold.setdefault(question_id, []).append((document_id, filename))
        return gold

    async def find_documents(
        self,
        *,
        filenames: Sequence[str],
        content_hashes: Sequence[str],
        corpus_id: uuid.UUID | None,
    ) -> Sequence[Document]:
        """Documents matching any of the names or hashes, within a corpus when one is given."""
        if not filenames and not content_hashes:
            return []
        stmt = select(Document).where(
            (Document.filename.in_(filenames))
            | (Document.content_hash.in_(content_hashes))
        )
        if corpus_id is not None:
            stmt = stmt.join(
                CorpusDocument, CorpusDocument.document_id == Document.id
            ).where(CorpusDocument.corpus_id == corpus_id)
        return (
            await self.session.scalars(stmt.order_by(Document.filename, Document.id))
        ).all()


class QASetSnapshotRepository:
    """Data access for `qa_set_snapshots` and their composition."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, snapshot: QASetSnapshot) -> QASetSnapshot:
        self.session.add(snapshot)
        return snapshot

    async def get_by_id(self, snapshot_id: uuid.UUID) -> QASetSnapshot | None:
        return await self.session.get(QASetSnapshot, snapshot_id)

    async def get_by_composition(
        self, qa_set_id: uuid.UUID, composition_hash: str
    ) -> QASetSnapshot | None:
        stmt = select(QASetSnapshot).where(
            QASetSnapshot.qa_set_id == qa_set_id,
            QASetSnapshot.composition_hash == composition_hash,
        )
        return await self.session.scalar(stmt)

    async def list_by_set(
        self, qa_set_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> Sequence[QASetSnapshot]:
        stmt = (
            select(QASetSnapshot)
            .where(QASetSnapshot.qa_set_id == qa_set_id)
            .order_by(QASetSnapshot.frozen_at.desc(), QASetSnapshot.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return (await self.session.scalars(stmt)).all()

    async def count_by_set(self, qa_set_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(QASetSnapshot)
            .where(QASetSnapshot.qa_set_id == qa_set_id)
        )
        return await self.session.scalar(stmt) or 0

    async def add_questions(
        self, snapshot_id: uuid.UUID, question_ids: Sequence[uuid.UUID]
    ) -> None:
        await self.session.execute(
            pg_insert(QASnapshotQuestion).values(
                [
                    {"snapshot_id": snapshot_id, "question_id": question_id}
                    for question_id in question_ids
                ]
            )
        )

    async def question_ids(self, snapshot_id: uuid.UUID) -> list[uuid.UUID]:
        """Questions of a snapshot in a stable order."""
        stmt = (
            select(QASnapshotQuestion.question_id)
            .where(QASnapshotQuestion.snapshot_id == snapshot_id)
            .order_by(QASnapshotQuestion.question_id)
        )
        return list((await self.session.scalars(stmt)).all())


class EvidenceRepository:
    """Data access for `evidence_links` and `evidence_link_chunks`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self, question_id: uuid.UUID, chunking_configuration_id: uuid.UUID
    ) -> EvidenceLink | None:
        stmt = (
            select(EvidenceLink)
            .where(
                EvidenceLink.question_id == question_id,
                EvidenceLink.chunking_configuration_id == chunking_configuration_id,
            )
            # The upsert writes with a plain statement, so a row already in the session
            # would otherwise be returned with its stale values.
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(stmt)

    async def upsert(
        self,
        question_id: uuid.UUID,
        chunking_configuration_id: uuid.UUID,
        *,
        status: EvidenceLinkStatus,
        confirmed_by: str | None,
        confirmed_at: object,
    ) -> uuid.UUID:
        """Write the link of a question under a configuration, creating it if needed.

        One statement on the unique pair, so two people saving the same link at once end
        with one row and the last write, instead of a duplicate-key error.
        """
        values = {
            "status": status,
            "confirmed_by": confirmed_by,
            "confirmed_at": confirmed_at,
        }
        stmt = (
            pg_insert(EvidenceLink)
            .values(
                question_id=question_id,
                chunking_configuration_id=chunking_configuration_id,
                **values,
            )
            .on_conflict_do_update(
                index_elements=["question_id", "chunking_configuration_id"],
                set_=values,
            )
            .returning(EvidenceLink.id)
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def replace_chunks(
        self, evidence_link_id: uuid.UUID, rows: Sequence[dict]
    ) -> None:
        await self.session.execute(
            delete(EvidenceLinkChunk).where(
                EvidenceLinkChunk.evidence_link_id == evidence_link_id
            )
        )
        if rows:
            await self.session.execute(
                pg_insert(EvidenceLinkChunk).values(
                    [{"evidence_link_id": evidence_link_id, **row} for row in rows]
                )
            )

    async def chunks_of_link(
        self, evidence_link_id: uuid.UUID
    ) -> list[tuple[EvidenceLinkChunk, Chunk, uuid.UUID, str]]:
        """Chunks of a link with their document id and file name, in reading order."""
        stmt = (
            select(EvidenceLinkChunk, Chunk, Document.id, Document.filename)
            .join(Chunk, Chunk.id == EvidenceLinkChunk.chunk_id)
            .join(ChunkResult, ChunkResult.id == Chunk.chunk_result_id)
            .join(Document, Document.id == ChunkResult.document_id)
            .where(EvidenceLinkChunk.evidence_link_id == evidence_link_id)
            .order_by(Document.filename, Document.id, Chunk.ordinal)
        )
        return [tuple(row) for row in (await self.session.execute(stmt)).all()]

    async def chunk_documents(
        self, chunk_ids: Sequence[uuid.UUID], chunking_configuration_id: uuid.UUID
    ) -> dict[uuid.UUID, uuid.UUID]:
        """Document of each chunk, for the chunks that exist under the configuration."""
        if not chunk_ids:
            return {}
        stmt = (
            select(Chunk.id, ChunkResult.document_id)
            .join(ChunkResult, ChunkResult.id == Chunk.chunk_result_id)
            .where(
                Chunk.id.in_(chunk_ids),
                ChunkResult.chunking_configuration_id == chunking_configuration_id,
            )
        )
        return dict((await self.session.execute(stmt)).all())

    async def statuses(
        self, question_ids: Sequence[uuid.UUID], chunking_configuration_id: uuid.UUID
    ) -> dict[uuid.UUID, EvidenceLinkStatus]:
        """Status of the link of each question that has one under the configuration."""
        if not question_ids:
            return {}
        stmt = select(EvidenceLink.question_id, EvidenceLink.status).where(
            EvidenceLink.question_id.in_(question_ids),
            EvidenceLink.chunking_configuration_id == chunking_configuration_id,
        )
        return dict((await self.session.execute(stmt)).all())

    async def documents_with_confirmed_chunks(
        self, question_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
    ) -> set[uuid.UUID]:
        """The documents, among these, holding a confirmed chunk of the question.

        Across every chunking configuration: a document that is evidence in any of them
        must stay gold.
        """
        if not document_ids:
            return set()
        stmt = (
            select(ChunkResult.document_id)
            .join(Chunk, Chunk.chunk_result_id == ChunkResult.id)
            .join(EvidenceLinkChunk, EvidenceLinkChunk.chunk_id == Chunk.id)
            .join(EvidenceLink, EvidenceLink.id == EvidenceLinkChunk.evidence_link_id)
            .where(
                EvidenceLink.question_id == question_id,
                EvidenceLink.status == EvidenceLinkStatus.CONFIRMED,
                ChunkResult.document_id.in_(document_ids),
            )
            .distinct()
        )
        return set((await self.session.scalars(stmt)).all())
