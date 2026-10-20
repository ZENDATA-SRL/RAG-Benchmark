from __future__ import annotations

from src.core.exceptions import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)


class MaterializationError(DomainError):
    """Base class for chunk materialisation errors."""

    code = "materialization_error"


class MaterializationRunNotFoundError(NotFoundError, MaterializationError):
    """Raised when a referenced materialisation run does not exist."""

    code = "materialization_run_not_found"

    def __init__(self, run_id: object) -> None:
        super().__init__(
            f"materialization run not found: {run_id}",
            details={"materialization_run_id": str(run_id)},
        )
        self.run_id = run_id


class DocumentsNotStoredError(ValidationError, MaterializationError):
    """Raised when a materialisation is requested on documents that are not `stored`.

    Names the offending documents rather than only the count: a user who selected fifty
    files needs to know which of them to fix.
    """

    code = "documents_not_stored"

    def __init__(self, offending: dict[str, str]) -> None:
        listed = ", ".join(
            f"{doc_id} ({status})" for doc_id, status in offending.items()
        )
        super().__init__(
            f"materialisation needs every document to be stored; not stored: {listed}",
            details={"documents": offending, "expected_status": "stored"},
        )
        self.offending = offending


class EmptyMaterializationError(ValidationError, MaterializationError):
    """Raised when a materialisation would run on no document at all.

    Refused instead of launching an empty workflow, because the deterministic id of an empty
    document set is the same for every configuration and would silently collide.
    """

    code = "empty_materialization"

    def __init__(self) -> None:
        super().__init__("a materialisation needs at least one document")


class MaterializationNotCancellableError(ConflictError, MaterializationError):
    """Raised when cancellation is requested on a run that already finished."""

    code = "materialization_not_cancellable"

    def __init__(self, run_id: object, status: object) -> None:
        super().__init__(
            f"materialization run {run_id} is not running (status={status})",
            details={"materialization_run_id": str(run_id), "status": str(status)},
        )
        self.run_id = run_id
        self.status = status
