from __future__ import annotations


class CorpusError(Exception):
    """Base class for corpus domain errors."""


class DocumentsNotInCorpusError(CorpusError):
    """Raised when a snapshot is requested over documents the corpus does not contain."""

    def __init__(self, document_ids: list[str]) -> None:
        super().__init__(f"documents not in corpus: {', '.join(document_ids)}")
        self.document_ids = document_ids


class EmptySnapshotError(CorpusError):
    """Raised when a snapshot is requested with no documents."""

    def __init__(self) -> None:
        super().__init__("a corpus snapshot must contain at least one document")
