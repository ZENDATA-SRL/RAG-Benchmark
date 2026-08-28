from __future__ import annotations

from src.core.exceptions import DomainError, ValidationError


class CorpusError(DomainError):
    """Base class for corpus domain errors."""

    code = "corpus_error"


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
