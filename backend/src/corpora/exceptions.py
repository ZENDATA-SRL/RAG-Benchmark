from __future__ import annotations

from src.core.exceptions import ConflictError, DomainError, NotFoundError, ValidationError


class CorpusError(DomainError):
    """Base class for corpus domain errors."""

    code = "corpus_error"


class CorpusNotFoundError(NotFoundError, CorpusError):
    """Raised when a corpus does not exist."""

    code = "corpus_not_found"

    def __init__(self, corpus_id: object) -> None:
        super().__init__(
            f"corpus not found: {corpus_id}",
            details={"corpus_id": str(corpus_id)},
        )
        self.corpus_id = corpus_id


class CorpusHasSnapshotsError(ConflictError, CorpusError):
    """Raised when a corpus with frozen snapshots is deleted (RF-C05).

    Deleting it would invalidate the compositions the experiments already measured, so the
    snapshots are what makes a metric interpretable and the corpus cannot outlive them.
    """

    code = "corpus_has_snapshots"

    def __init__(self, corpus_id: object, snapshot_count: int) -> None:
        super().__init__(
            f"corpus {corpus_id} has {snapshot_count} snapshot(s) and cannot be deleted",
            details={"corpus_id": str(corpus_id), "snapshot_count": snapshot_count},
        )
        self.corpus_id = corpus_id
        self.snapshot_count = snapshot_count


class UnknownDocumentsError(ValidationError, CorpusError):
    """Raised when documents are added to a corpus by ids that do not exist."""

    code = "unknown_documents"

    def __init__(self, document_ids: list[str]) -> None:
        super().__init__(
            f"unknown documents: {', '.join(document_ids)}",
            details={"document_ids": document_ids},
        )
        self.document_ids = document_ids


class DocumentsNotInCorpusError(ValidationError, CorpusError):
    """Raised when a snapshot is requested over documents the corpus does not contain."""

    code = "documents_not_in_corpus"

    def __init__(self, document_ids: list[str]) -> None:
        super().__init__(
            f"documents not in corpus: {', '.join(document_ids)}",
            details={"document_ids": document_ids},
        )
        self.document_ids = document_ids


class EmptySnapshotError(ValidationError, CorpusError):
    """Raised when a snapshot is requested with no documents."""

    code = "empty_snapshot"

    def __init__(self) -> None:
        super().__init__("a corpus snapshot must contain at least one document")
