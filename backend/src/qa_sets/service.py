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
from src.infrastructure.database.enums import EvidenceLinkStatus
from src.pipelines.exceptions import ChunkingConfigurationNotFoundError
from src.pipelines.repository import ChunkingConfigurationRepository
from src.qa_sets.exceptions import (
    DocumentsOutsideCorpusError,
    DuplicateQuestionError,
    EmptyQASetError,
    GoldDocumentHasEvidenceError,
    QASetNotFoundError,
    QASetSnapshotNotFoundError,
    QuestionFrozenError,
    QuestionNotFoundError,
    QuestionReplacedError,
)
from src.qa_sets.models import ExpectedAnswer, QASet, QASetSnapshot, Question
from src.qa_sets.repository import (
    EvidenceRepository,
    QASetRepository,
    QASetSnapshotRepository,
    QuestionRepository,
)
from src.qa_sets.utils import (
    ExportFormat,
    ExportRow,
    ImportRow,
    content_hash_of,
    parse_import,
    recall_ceiling,
    render_export,
)

# Evidence status of a question with no link under a configuration: never reviewed, which
# is different from a reviewed link whose evidence was not found.
NOT_REVIEWED = "not_reviewed"


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
    """A question with its gold documents and expected answers, as the API lists it.

    `frozen` says whether a snapshot holds it, hence whether it can still be edited.
    `evidence_status` is the state of its evidence under the chunking configuration the
    caller asked about, `None` when none was asked.
    """

    id: uuid.UUID
    qa_set_id: uuid.UUID
    text: str
    tags: list[str]
    answerable: bool
    gold_documents: list[GoldRef]
    expected_answers: list[AnswerRef]
    frozen: bool
    replaced_by_question_id: uuid.UUID | None = None
    evidence_status: str | None = None


@dataclasses.dataclass(frozen=True)
class QuestionDraft:
    """The editable content of a question, as authored in the UI."""

    text: str
    tags: list[str]
    answerable: bool
    expected_answers: list[AnswerRef]
    gold_document_ids: list[uuid.UUID]


@dataclasses.dataclass(frozen=True)
class EvidenceCoverage:
    """How far the evidence of a set has been reviewed under one configuration.

    Counted on the answerable questions of the set; the others have no evidence to find.
    """

    qa_set_id: uuid.UUID
    chunking_configuration_id: uuid.UUID
    answerable: int
    not_answerable: int
    confirmed: int
    not_found: int
    to_review: int
    not_reviewed: int

    @property
    def recall_ceiling(self) -> float | None:
        return recall_ceiling(self.confirmed, self.not_found)


@dataclasses.dataclass(frozen=True)
class ExportFile:
    filename: str
    media_type: str
    content: str


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
        self,
        qa_set_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        chunking_configuration_id: uuid.UUID | None = None,
    ) -> tuple[list[QuestionView], int]:
        """One page of the current questions of a set, and their total.

        Replaced questions are left out: they only live on in the snapshots that hold them.
        With a chunking configuration each question also carries the status of its
        evidence under it.

        Raises:
            QASetNotFoundError: If the set does not exist.
            ChunkingConfigurationNotFoundError: If the configuration does not exist.
        """
        await self.get(qa_set_id)
        if chunking_configuration_id is not None:
            await self.require_configuration(chunking_configuration_id)
        questions = await self.questions.list_by_set(
            qa_set_id, limit=limit, offset=offset
        )
        views = await self.views(questions, chunking_configuration_id)
        return views, await self.questions.count_by_set(qa_set_id)

    async def views(
        self,
        questions: Sequence[Question],
        chunking_configuration_id: uuid.UUID | None = None,
    ) -> list[QuestionView]:
        """Questions with gold documents, answers, frozen flag and evidence status."""
        question_ids = [question.id for question in questions]
        gold = await self.questions.gold_by_question(question_ids)
        answers = await self.questions.answers_by_question(question_ids)
        frozen = await self.questions.frozen_ids(question_ids)
        statuses = (
            await EvidenceRepository(self.session).statuses(
                question_ids, chunking_configuration_id
            )
            if chunking_configuration_id is not None
            else {}
        )
        return [
            QuestionView(
                id=question.id,
                qa_set_id=question.qa_set_id,
                text=question.text,
                tags=list(question.tags),
                answerable=question.answerable,
                gold_documents=[GoldRef(*ref) for ref in gold.get(question.id, [])],
                expected_answers=[
                    AnswerRef(answer.text, answer.is_primary)
                    for answer in answers.get(question.id, [])
                ],
                frozen=question.id in frozen,
                replaced_by_question_id=question.replaced_by_question_id,
                evidence_status=(
                    None
                    if chunking_configuration_id is None
                    else _status_value(statuses.get(question.id))
                ),
            )
            for question in questions
        ]

    async def require_configuration(self, chunking_configuration_id: uuid.UUID) -> None:
        """Check that a chunking configuration exists.

        Raises:
            ChunkingConfigurationNotFoundError: If it does not.
        """
        repository = ChunkingConfigurationRepository(self.session)
        if await repository.get_by_id(chunking_configuration_id) is None:
            raise ChunkingConfigurationNotFoundError(chunking_configuration_id)

    async def evidence_coverage(
        self, qa_set_id: uuid.UUID, chunking_configuration_id: uuid.UUID
    ) -> EvidenceCoverage:
        """Count the current questions of a set by the status of their evidence.

        Raises:
            QASetNotFoundError: If the set does not exist.
            ChunkingConfigurationNotFoundError: If the configuration does not exist.
        """
        await self.get(qa_set_id)
        await self.require_configuration(chunking_configuration_id)
        answerable = await self.questions.answerable_ids_by_set(qa_set_id)
        total = await self.questions.count_by_set(qa_set_id)
        statuses = await EvidenceRepository(self.session).statuses(
            answerable, chunking_configuration_id
        )
        counts = {status: 0 for status in EvidenceLinkStatus}
        for status in statuses.values():
            counts[status] += 1
        return EvidenceCoverage(
            qa_set_id=qa_set_id,
            chunking_configuration_id=chunking_configuration_id,
            answerable=len(answerable),
            not_answerable=total - len(answerable),
            confirmed=counts[EvidenceLinkStatus.CONFIRMED],
            not_found=counts[EvidenceLinkStatus.NOT_FOUND],
            to_review=counts[EvidenceLinkStatus.TO_REVIEW],
            not_reviewed=len(answerable) - len(statuses),
        )

    async def export(
        self,
        qa_set_id: uuid.UUID,
        export_format: ExportFormat,
        *,
        snapshot_id: uuid.UUID | None = None,
    ) -> ExportFile:
        """Export questions in the same format the import reads.

        The current questions of the set, or those of one of its snapshots. Gold files
        are written by name, or by `sha256:` when another document in the corpus carries
        the same name, so that importing the file back never meets an ambiguous name.
        Only the primary expected answer is written, because the import reads one. The
        evidence chunks are not exported: they are ids of one installation's chunks, not
        something another installation could resolve.

        Raises:
            QASetNotFoundError: If the set does not exist.
            QASetSnapshotNotFoundError: If the snapshot does not exist in this set.
        """
        qa_set = await self.get(qa_set_id)
        if snapshot_id is None:
            question_ids = await self.questions.ids_by_set(qa_set_id)
        else:
            snapshot = await QASetSnapshotRepository(self.session).get_by_id(
                snapshot_id
            )
            if snapshot is None or snapshot.qa_set_id != qa_set_id:
                raise QASetSnapshotNotFoundError(snapshot_id)
            question_ids = await QASetSnapshotRepository(self.session).question_ids(
                snapshot_id
            )
        questions = await self.questions.list_by_ids(question_ids)
        answers = await self.questions.answers_by_question(question_ids)
        files = await self.questions.gold_files_by_question(question_ids)
        ambiguous = await self.questions.ambiguous_filenames(
            sorted({name for refs in files.values() for name, _ in refs}),
            qa_set.origin_corpus_id,
        )
        rows = []
        for question in questions:
            primary = next(
                (a for a in answers.get(question.id, []) if a.is_primary), None
            )
            rows.append(
                ExportRow(
                    question=question.text,
                    answer=primary.text if primary else None,
                    gold_files=[
                        f"sha256:{digest}" if name in ambiguous else name
                        for name, digest in files.get(question.id, [])
                    ],
                    tags=list(question.tags),
                    answerable=question.answerable,
                )
            )
        content, media_type = render_export(rows, export_format)
        return ExportFile(
            filename=f"{_slug(qa_set.name)}.{export_format.value}",
            media_type=media_type,
            content=content,
        )

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


class QuestionService:
    """Authoring of single questions: create, edit until frozen, replace, delete.

    A question held by a snapshot is never edited, because snapshots reference questions
    and a past experiment would silently change meaning; it is replaced by a new question
    instead. Gold documents are an annotation rather than part of the question, so they
    can change on a frozen question too.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.qa_sets = QASetService(session)
        self.questions = QuestionRepository(session)
        self.evidence = EvidenceRepository(session)

    async def get(self, question_id: uuid.UUID) -> Question:
        """Return a question.

        Raises:
            QuestionNotFoundError: If it does not exist.
        """
        question = await self.questions.get_by_id(question_id)
        if question is None:
            raise QuestionNotFoundError(question_id)
        return question

    async def view(
        self, question_id: uuid.UUID, chunking_configuration_id: uuid.UUID | None = None
    ) -> QuestionView:
        """Return a question as the API shows it.

        Raises:
            QuestionNotFoundError: If it does not exist.
        """
        question = await self.get(question_id)
        return (await self.qa_sets.views([question], chunking_configuration_id))[0]

    async def create(self, qa_set_id: uuid.UUID, draft: QuestionDraft) -> QuestionView:
        """Add a question to a set.

        Gold documents are optional: they are also derived later from the chunks a person
        confirms as evidence.

        Raises:
            QASetNotFoundError: If the set does not exist.
            DuplicateQuestionError: If the set already has a question with this text.
            DocumentsOutsideCorpusError: If a gold document is not in the origin corpus.
        """
        qa_set = await self.qa_sets.get(qa_set_id)
        await self._check_unique_text(qa_set_id, draft.text)
        await self._check_documents(qa_set, draft.gold_document_ids)
        question = await self._insert(qa_set_id, draft)
        return await self.view(question.id)

    async def update(
        self,
        question_id: uuid.UUID,
        *,
        text: str | None = None,
        tags: list[str] | None = None,
        answerable: bool | None = None,
        expected_answers: list[AnswerRef] | None = None,
    ) -> QuestionView:
        """Edit a question that no snapshot holds yet; `None` leaves a field as it is.

        Its evidence links are kept: until it is frozen the question is a draft, and the
        person editing it is the one who reviews the evidence.

        Raises:
            QuestionNotFoundError: If it does not exist.
            QuestionReplacedError: If it already has a successor.
            QuestionFrozenError: If a snapshot holds it.
            DuplicateQuestionError: If the new text is already in the set.
        """
        question = await self._editable(question_id)
        if text is not None and text != question.text:
            await self._check_unique_text(question.qa_set_id, text)
            question.text = text
        if tags is not None:
            question.tags = tags
        if answerable is not None:
            question.answerable = answerable
        if expected_answers is not None:
            await self.questions.replace_expected_answers(
                question.id, _answers(question.id, expected_answers)
            )
        await self.session.flush()
        return await self.view(question.id)

    async def delete(self, question_id: uuid.UUID) -> None:
        """Delete a question that no snapshot holds, with its answers and evidence.

        Deleting the successor of a replaced question brings the replaced one back into
        the set, which is how a replacement is undone.

        Raises:
            QuestionNotFoundError: If it does not exist.
            QuestionFrozenError: If a snapshot holds it.
        """
        question = await self.get(question_id)
        if await self.questions.frozen_ids([question.id]):
            raise QuestionFrozenError(question.id)
        await self.questions.delete(question)
        await self.session.flush()

    async def replace(
        self, question_id: uuid.UUID, draft: QuestionDraft
    ) -> QuestionView:
        """Replace a question with a new one, leaving the old one to its snapshots.

        The old question leaves the current set, so the next freeze holds the new one, and
        the snapshots that hold the old one are untouched. Evidence links are not copied:
        the question changed, so its evidence has to be reviewed again.

        Raises:
            QuestionNotFoundError: If it does not exist.
            QuestionReplacedError: If it was already replaced.
            DuplicateQuestionError: If another current question has the new text.
            DocumentsOutsideCorpusError: If a gold document is not in the origin corpus.
        """
        old = await self.get(question_id)
        if old.replaced_by_question_id is not None:
            raise QuestionReplacedError(old.id, old.replaced_by_question_id)
        qa_set = await self.qa_sets.get(old.qa_set_id)
        await self._check_unique_text(old.qa_set_id, draft.text, ignore=old.id)
        await self._check_documents(qa_set, draft.gold_document_ids)
        new = await self._insert(old.qa_set_id, draft)
        old.replaced_by_question_id = new.id
        await self.session.flush()
        return await self.view(new.id)

    async def set_gold_documents(
        self, question_id: uuid.UUID, document_ids: list[uuid.UUID]
    ) -> QuestionView:
        """Set the gold documents of a question to exactly this list.

        Allowed on frozen questions: the gold is an annotation of the question, and the
        evidence a person confirms adds to it anyway. A document that holds confirmed
        evidence chunks cannot be removed, or the evidence would point outside the gold.

        Raises:
            QuestionNotFoundError: If it does not exist.
            DocumentsOutsideCorpusError: If a document is not in the origin corpus.
            GoldDocumentHasEvidenceError: If a removed document holds confirmed evidence.
        """
        question = await self.get(question_id)
        qa_set = await self.qa_sets.get(question.qa_set_id)
        await self._check_documents(qa_set, document_ids)
        current = await self.questions.gold_document_ids(question.id)
        removed = sorted(current - set(document_ids))
        blocked = await self.evidence.documents_with_confirmed_chunks(
            question.id, removed
        )
        if blocked:
            raise GoldDocumentHasEvidenceError(sorted(blocked))
        await self.questions.remove_gold_documents(question.id, removed)
        await self.questions.add_gold_documents(
            question.id, [d for d in document_ids if d not in current]
        )
        await self.session.flush()
        return await self.view(question.id)

    async def _editable(self, question_id: uuid.UUID) -> Question:
        question = await self.get(question_id)
        if question.replaced_by_question_id is not None:
            raise QuestionReplacedError(question.id, question.replaced_by_question_id)
        if await self.questions.frozen_ids([question.id]):
            raise QuestionFrozenError(question.id)
        return question

    async def _check_unique_text(
        self, qa_set_id: uuid.UUID, text: str, *, ignore: uuid.UUID | None = None
    ) -> None:
        existing = await self.questions.active_with_text(qa_set_id, text)
        if existing is not None and existing != ignore:
            raise DuplicateQuestionError(text, existing)

    async def _check_documents(
        self, qa_set: QASet, document_ids: Sequence[uuid.UUID]
    ) -> None:
        found = await self.questions.existing_documents(
            document_ids, qa_set.origin_corpus_id
        )
        missing = [d for d in document_ids if d not in found]
        if missing:
            raise DocumentsOutsideCorpusError(missing)

    async def _insert(self, qa_set_id: uuid.UUID, draft: QuestionDraft) -> Question:
        question = self.questions.add(
            Question(
                qa_set_id=qa_set_id,
                text=draft.text,
                tags=draft.tags,
                answerable=draft.answerable,
                # Stamped by the application, like an import, so questions created in one
                # transaction keep their order in the listing.
                created_at=dt.datetime.now(dt.UTC),
            )
        )
        await self.session.flush()
        await self.questions.add_gold_documents(question.id, draft.gold_document_ids)
        self.session.add_all(_answers(question.id, draft.expected_answers))
        await self.session.flush()
        return question


def _answers(
    question_id: uuid.UUID, answers: Sequence[AnswerRef]
) -> list[ExpectedAnswer]:
    """Expected answer rows, with exactly one primary when there is any answer.

    The primary answer is the reference handed to a judge; when none is marked, the
    first one is.
    """
    has_primary = any(answer.is_primary for answer in answers)
    return [
        ExpectedAnswer(
            question_id=question_id,
            text=answer.text,
            is_primary=answer.is_primary if has_primary else index == 0,
        )
        for index, answer in enumerate(answers)
    ]


def _status_value(status: EvidenceLinkStatus | None) -> str:
    return status.value if status is not None else NOT_REVIEWED


def _slug(name: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")
    return "-".join(part for part in slug.split("-") if part) or "qa-set"


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
