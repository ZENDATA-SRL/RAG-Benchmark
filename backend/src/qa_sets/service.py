from __future__ import annotations

import dataclasses
import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.get_or_create import get_or_create_reporting
from src.core.hashing import composition_hash
from src.corpora.exceptions import CorpusNotFoundError
from src.corpora.repository import CorpusRepository
from src.documents.models import Document
from src.qa_sets.exceptions import (
    EmptyQASetError,
    QASetNotFoundError,
    QASetSnapshotNotFoundError,
)
from src.qa_sets.models import ExpectedAnswer, QASet, QASetSnapshot, Question
from src.qa_sets.repository import (
    QASetRepository,
    QASetSnapshotRepository,
    QuestionRepository,
)
from src.qa_sets.utils import ImportRow, content_hash_of, parse_import


@dataclasses.dataclass(frozen=True)
class GoldRef:
    document_id: uuid.UUID
    filename: str


@dataclasses.dataclass(frozen=True)
class AnswerRef:
    text: str
    is_primary: bool


@dataclasses.dataclass(frozen=True)
class QuestionView:
    """A question with its gold documents and expected answers, as the API lists it."""

    id: uuid.UUID
    text: str
    tags: list[str]
    answerable: bool
    gold_documents: list[GoldRef]
    expected_answers: list[AnswerRef]


@dataclasses.dataclass(frozen=True)
class ImportedQuestion:
    row: int
    question_id: uuid.UUID
    text: str
    gold_documents: list[GoldRef]


@dataclasses.dataclass(frozen=True)
class UnresolvedRow:
    row: int
    question: str
    files: list[str]


@dataclasses.dataclass(frozen=True)
class AmbiguousCandidate:
    document_id: uuid.UUID
    filename: str
    content_hash: str


@dataclasses.dataclass(frozen=True)
class AmbiguousFile:
    file: str
    candidates: list[AmbiguousCandidate]


@dataclasses.dataclass(frozen=True)
class AmbiguousRow:
    row: int
    question: str
    files: list[AmbiguousFile]


@dataclasses.dataclass(frozen=True)
class InvalidRow:
    row: int
    question: str
    reason: str


@dataclasses.dataclass
class ImportSummary:
    """Outcome of an import, row by row."""

    qa_set_id: uuid.UUID
    total_rows: int = 0
    imported: list[ImportedQuestion] = dataclasses.field(default_factory=list)
    existing: list[ImportedQuestion] = dataclasses.field(default_factory=list)
    unresolved: list[UnresolvedRow] = dataclasses.field(default_factory=list)
    ambiguous: list[AmbiguousRow] = dataclasses.field(default_factory=list)
    invalid: list[InvalidRow] = dataclasses.field(default_factory=list)


class QASetService:
    """QA sets, their questions with gold documents and answers, and their import."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.qa_sets = QASetRepository(session)
        self.questions = QuestionRepository(session)
        self.corpora = CorpusRepository(session)

    async def create(
        self,
        name: str,
        description: str | None = None,
        origin_corpus_id: uuid.UUID | None = None,
    ) -> QASet:
        """Create a QA set.

        Raises:
            CorpusNotFoundError: If `origin_corpus_id` does not exist.
        """
        if (
            origin_corpus_id is not None
            and await self.corpora.get_by_id(origin_corpus_id) is None
        ):
            raise CorpusNotFoundError(origin_corpus_id)
        qa_set = self.qa_sets.add(
            QASet(name=name, description=description, origin_corpus_id=origin_corpus_id)
        )
        await self.session.flush()
        await self.session.refresh(qa_set)
        return qa_set

    async def get(self, qa_set_id: uuid.UUID) -> QASet:
        """Return a QA set.

        Raises:
            QASetNotFoundError: If it does not exist.
        """
        qa_set = await self.qa_sets.get_by_id(qa_set_id)
        if qa_set is None:
            raise QASetNotFoundError(qa_set_id)
        return qa_set

    async def list(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[QASet], dict[uuid.UUID, int], int]:
        """One page of sets, newest first, their question counts and the total."""
        qa_sets = await self.qa_sets.list(limit=limit, offset=offset)
        counts = await self.qa_sets.question_counts([qa_set.id for qa_set in qa_sets])
        return qa_sets, counts, await self.qa_sets.count()

    async def question_count(self, qa_set_id: uuid.UUID) -> int:
        return await self.questions.count_by_set(qa_set_id)

    async def list_questions(
        self, qa_set_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[QuestionView], int]:
        """One page of the questions of a set with gold documents and answers, and the total.

        Raises:
            QASetNotFoundError: If the set does not exist.
        """
        await self.get(qa_set_id)
        questions = await self.questions.list_by_set(
            qa_set_id, limit=limit, offset=offset
        )
        question_ids = [question.id for question in questions]
        gold = await self.questions.gold_by_question(question_ids)
        answers = await self.questions.answers_by_question(question_ids)
        views = [
            QuestionView(
                id=question.id,
                text=question.text,
                tags=list(question.tags),
                answerable=question.answerable,
                gold_documents=[GoldRef(*ref) for ref in gold.get(question.id, [])],
                expected_answers=[
                    AnswerRef(answer.text, answer.is_primary)
                    for answer in answers.get(question.id, [])
                ],
            )
            for question in questions
        ]
        return views, await self.questions.count_by_set(qa_set_id)

    async def import_file(
        self, qa_set_id: uuid.UUID, filename: str, data: bytes
    ) -> ImportSummary:
        """Import questions with their gold files and expected answer from a CSV or JSONL file.

        The import stops at the gold documents: which chunks hold the answer is not in the
        file, because it depends on a chunking configuration the file knows nothing about,
        and is confirmed by a person afterwards. Gold files are resolved among the documents of the set's origin corpus (every
        document when the set has none), by file name or, when the entry is a sha-256, by
        content hash. A row whose files cannot be resolved with certainty is not imported
        and is listed in the summary with the reason: a name shared by two documents is
        reported as ambiguous and never resolved by guessing. Questions whose text is
        already in the set are left untouched, so importing the same file twice adds
        nothing.

        Args:
            qa_set_id: Set receiving the questions.
            filename: Name of the uploaded file, which selects the format.
            data: Raw content of the file.

        Raises:
            QASetNotFoundError: If the set does not exist.
            UnsupportedImportFormatError: If the file is neither CSV nor JSONL.
            InvalidImportFileError: If the file cannot be read.
        """
        qa_set = await self.get(qa_set_id)
        rows = parse_import(filename, data)
        summary = ImportSummary(qa_set_id=qa_set.id, total_rows=len(rows))

        references = {
            ref for row in rows if row.error is None for ref in row.gold_files
        }
        hashes = {h for ref in references if (h := content_hash_of(ref))}
        documents = await self.questions.find_documents(
            filenames=sorted(references - hashes),
            content_hashes=sorted(hashes),
            corpus_id=qa_set.origin_corpus_id,
        )
        by_name: dict[str, list[Document]] = {}
        by_hash: dict[str, Document] = {}
        for document in documents:
            by_name.setdefault(document.filename, []).append(document)
            by_hash[document.content_hash] = document

        known = await self.questions.texts_in_set(qa_set.id)
        for row in rows:
            await self._import_row(summary, row, known, by_name, by_hash)
        await self.session.flush()
        return summary

    async def _import_row(
        self,
        summary: ImportSummary,
        row: ImportRow,
        known: dict[str, uuid.UUID],
        by_name: dict[str, list[Document]],
        by_hash: dict[str, Document],
    ) -> None:
        if row.error is not None:
            summary.invalid.append(InvalidRow(row.row, row.question, row.error))
            return

        resolved: dict[uuid.UUID, Document] = {}
        unresolved: list[str] = []
        ambiguous: list[AmbiguousFile] = []
        for reference in row.gold_files:
            digest = content_hash_of(reference)
            candidates = (
                [by_hash[digest]]
                if digest in by_hash
                else []
                if digest
                else by_name.get(reference, [])
            )
            if not candidates:
                unresolved.append(reference)
            elif len(candidates) > 1:
                ambiguous.append(
                    AmbiguousFile(
                        reference,
                        [
                            AmbiguousCandidate(d.id, d.filename, d.content_hash)
                            for d in candidates
                        ],
                    )
                )
            else:
                resolved[candidates[0].id] = candidates[0]
        if unresolved or ambiguous:
            if unresolved:
                summary.unresolved.append(
                    UnresolvedRow(row.row, row.question, unresolved)
                )
            if ambiguous:
                summary.ambiguous.append(AmbiguousRow(row.row, row.question, ambiguous))
            return

        gold = [
            GoldRef(document.id, document.filename) for document in resolved.values()
        ]
        if row.question in known:
            summary.existing.append(
                ImportedQuestion(row.row, known[row.question], row.question, gold)
            )
            return

        question = self.questions.add(
            Question(
                qa_set_id=summary.qa_set_id,
                text=row.question,
                tags=row.tags,
                answerable=row.answerable,
                # `now()` is the transaction time, identical for every question of one
                # import: stamping each one keeps the order of the file in the listing.
                created_at=dt.datetime.now(dt.UTC),
            )
        )
        await self.session.flush()
        await self.questions.add_gold_documents(question.id, list(resolved))
        if row.answer:
            self.questions.add_expected_answer(
                ExpectedAnswer(
                    question_id=question.id, text=row.answer, is_primary=True
                )
            )
        known[row.question] = question.id
        summary.imported.append(
            ImportedQuestion(row.row, question.id, row.question, gold)
        )


class QASetSnapshotService:
    """Freezing of the current questions of a set into an immutable snapshot."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.qa_sets = QASetService(session)
        self.questions = QuestionRepository(session)
        self.snapshots = QASetSnapshotRepository(session)

    async def get_or_create_reporting(
        self, qa_set_id: uuid.UUID, *, label: str | None = None
    ) -> tuple[QASetSnapshot, bool]:
        """Freeze the current questions, reusing the snapshot with the same composition.

        Deduplicated on `(qa_set_id, composition_hash)`: a metric is only comparable across
        runs of the same questions, so two snapshots of one composition would split them.

        Returns:
            The snapshot and whether this call created it.

        Raises:
            QASetNotFoundError: If the set does not exist.
            EmptyQASetError: If the set has no questions.
        """
        qa_set = await self.qa_sets.get(qa_set_id)
        question_ids = await self.questions.ids_by_set(qa_set_id)
        if not question_ids:
            raise EmptyQASetError(qa_set_id)
        digest = composition_hash(question_ids)

        async def create() -> QASetSnapshot:
            snapshot = self.snapshots.add(
                QASetSnapshot(
                    qa_set_id=qa_set_id,
                    label=label or f"{qa_set.name} · {len(question_ids)} questions",
                    question_count=len(question_ids),
                    composition_hash=digest,
                )
            )
            await self.session.flush()
            await self.snapshots.add_questions(snapshot.id, question_ids)
            return snapshot

        return await get_or_create_reporting(
            self.session,
            lookup=lambda: self.snapshots.get_by_composition(qa_set_id, digest),
            create=create,
        )

    async def get(self, snapshot_id: uuid.UUID) -> QASetSnapshot:
        """Return a snapshot.

        Raises:
            QASetSnapshotNotFoundError: If it does not exist.
        """
        snapshot = await self.snapshots.get_by_id(snapshot_id)
        if snapshot is None:
            raise QASetSnapshotNotFoundError(snapshot_id)
        return snapshot

    async def list(
        self, qa_set_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[QASetSnapshot], int]:
        """One page of the snapshots of a set, newest first, and the total.

        Raises:
            QASetNotFoundError: If the set does not exist.
        """
        await self.qa_sets.get(qa_set_id)
        return (
            await self.snapshots.list_by_set(qa_set_id, limit=limit, offset=offset),
            await self.snapshots.count_by_set(qa_set_id),
        )
