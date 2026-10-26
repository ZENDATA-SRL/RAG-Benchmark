from __future__ import annotations

from src.core.exceptions import DomainError, NotFoundError, ValidationError


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
