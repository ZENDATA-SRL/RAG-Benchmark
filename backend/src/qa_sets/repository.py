from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.corpora.models import CorpusDocument
from src.documents.models import Document
from src.qa_sets.models import (
    ExpectedAnswer,
    GoldDocument,
    QASet,
    QASetSnapshot,
    QASnapshotQuestion,
    Question,
)


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
            .where(Question.qa_set_id.in_(qa_set_ids))
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
        stmt = select(Question.text, Question.id).where(Question.qa_set_id == qa_set_id)
        return {
            text: question_id
            for text, question_id in (await self.session.execute(stmt)).all()
        }

    async def list_by_set(
        self, qa_set_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> Sequence[Question]:
        stmt = (
            select(Question)
            .where(Question.qa_set_id == qa_set_id)
            .order_by(Question.created_at, Question.id)
            .limit(limit)
            .offset(offset)
        )
        return (await self.session.scalars(stmt)).all()

    async def count_by_set(self, qa_set_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Question)
            .where(Question.qa_set_id == qa_set_id)
        )
        return await self.session.scalar(stmt) or 0

    async def list_by_ids(
        self, question_ids: Sequence[uuid.UUID]
    ) -> Sequence[Question]:
        if not question_ids:
            return []
        stmt = select(Question).where(Question.id.in_(question_ids))
        return (await self.session.scalars(stmt)).all()

    async def ids_by_set(self, qa_set_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(Question.id).where(Question.qa_set_id == qa_set_id)
        return list((await self.session.scalars(stmt)).all())

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
