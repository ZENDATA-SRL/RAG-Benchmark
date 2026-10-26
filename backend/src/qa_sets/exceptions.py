from __future__ import annotations

from src.core.exceptions import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)


class QASetError(DomainError):
    """Base class for QA set domain errors."""

    code = "qa_set_error"


class QASetNotFoundError(NotFoundError, QASetError):
    """Raised when a QA set does not exist."""

    code = "qa_set_not_found"

    def __init__(self, qa_set_id: object) -> None:
        super().__init__(
            f"qa set not found: {qa_set_id}", details={"qa_set_id": str(qa_set_id)}
        )
        self.qa_set_id = qa_set_id


class QASetSnapshotNotFoundError(NotFoundError, QASetError):
    """Raised when a QA set snapshot does not exist."""

    code = "qa_set_snapshot_not_found"

    def __init__(self, snapshot_id: object) -> None:
        super().__init__(
            f"qa set snapshot not found: {snapshot_id}",
            details={"snapshot_id": str(snapshot_id)},
        )
        self.snapshot_id = snapshot_id


class EmptyQASetError(ValidationError, QASetError):
    """Raised when a snapshot is frozen on a set without questions.

    An empty snapshot would be an experiment that measures nothing, so it is refused.
    """

    code = "empty_qa_set"

    def __init__(self, qa_set_id: object) -> None:
        super().__init__(
            f"qa set {qa_set_id} has no questions to freeze",
            details={"qa_set_id": str(qa_set_id)},
        )


class UnsupportedImportFormatError(ValidationError, QASetError):
    """Raised when an import file is neither CSV nor JSONL."""

    code = "unsupported_import_format"

    def __init__(self, filename: str) -> None:
        super().__init__(
            f"cannot import {filename!r}: use a .csv or .jsonl file",
            details={"filename": filename},
        )


class InvalidImportFileError(ValidationError, QASetError):
    """Raised when an import file cannot be read at all, as opposed to a bad row."""

    code = "invalid_import_file"

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"import file is not readable: {reason}", details={"reason": reason}
        )


class QuestionNotFoundError(NotFoundError, QASetError):
    """Raised when a question does not exist."""

    code = "question_not_found"

    def __init__(self, question_id: object) -> None:
        super().__init__(
            f"question not found: {question_id}",
            details={"question_id": str(question_id)},
        )


class QuestionFrozenError(ConflictError, QASetError):
    """Raised when a question held by a snapshot would be edited or deleted.

    Snapshots reference questions instead of copying them, so editing a frozen question
    would silently change what past experiments measured. It is replaced instead.
    """

    code = "question_frozen"

    def __init__(self, question_id: object) -> None:
        super().__init__(
            f"question {question_id} is frozen in a snapshot: replace it instead",
            details={"question_id": str(question_id)},
        )


class QuestionReplacedError(ConflictError, QASetError):
    """Raised when a question that already has a successor is changed or replaced again."""

    code = "question_replaced"

    def __init__(self, question_id: object, replaced_by: object) -> None:
        super().__init__(
            f"question {question_id} was replaced by {replaced_by}",
            details={"question_id": str(question_id), "replaced_by": str(replaced_by)},
        )


class DuplicateQuestionError(ConflictError, QASetError):
    """Raised when a set already has a question with the same text.

    The text is what an import deduplicates on, so two questions with one text would make
    a re-import ambiguous.
    """

    code = "question_already_in_set"

    def __init__(self, text: str, existing_id: object) -> None:
        super().__init__(
            "the set already has a question with this text",
            details={"text": text, "question_id": str(existing_id)},
        )


class DocumentsOutsideCorpusError(ValidationError, QASetError):
    """Raised when gold documents or evidence chunks are not in the set's origin corpus."""

    code = "documents_not_in_origin_corpus"

    def __init__(self, document_ids: list[object]) -> None:
        super().__init__(
            "some documents are not in the origin corpus of the set",
            details={"document_ids": [str(item) for item in document_ids]},
        )


class GoldDocumentHasEvidenceError(ConflictError, QASetError):
    """Raised when a gold document is removed while confirmed evidence chunks point into it.

    Removing it would leave confirmed chunks in a document that is no longer gold; the
    evidence has to be changed first.
    """

    code = "gold_document_has_evidence"

    def __init__(self, document_ids: list[object]) -> None:
        super().__init__(
            "confirmed evidence chunks come from these documents: change the evidence first",
            details={"document_ids": [str(item) for item in document_ids]},
        )


class InvalidEvidenceError(ValidationError, QASetError):
    """Raised when an evidence link breaks a rule of its status.

    `reason` is one of `question_not_answerable`, `chunks_required` (confirmed without
    chunks), `chunks_not_allowed` (not found with chunks), `annotator_required` (a decision
    without the person who took it).
    """

    code = "invalid_evidence"

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message, details={"reason": reason})
        self.reason = reason


class EvidenceChunksOutsideConfigurationError(ValidationError, QASetError):
    """Raised when evidence chunks do not exist under the link's chunking configuration."""

    code = "evidence_chunks_outside_configuration"

    def __init__(self, configuration_id: object, chunk_ids: list[object]) -> None:
        super().__init__(
            "some chunks do not belong to the chunking configuration of the link",
            details={
                "chunking_configuration_id": str(configuration_id),
                "chunk_ids": [str(item) for item in chunk_ids],
            },
        )
