from __future__ import annotations

from typing import Any

from src.core.exceptions import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)


class TransferError(DomainError):
    """Base class for transfer domain errors."""

    code = "transfer_error"


class TransferJobNotFoundError(NotFoundError, TransferError):
    """Raised when a transfer job does not exist."""

    code = "transfer_job_not_found"

    def __init__(self, transfer_job_id: object) -> None:
        super().__init__(
            f"transfer job not found: {transfer_job_id}",
            details={"transfer_job_id": str(transfer_job_id)},
        )


class QuestionNotInTransferError(NotFoundError, TransferError):
    """Raised when a question is asked of a job that does not include it."""

    code = "question_not_in_transfer"

    def __init__(self, transfer_job_id: object, question_id: object) -> None:
        super().__init__(
            f"question {question_id} is not part of transfer job {transfer_job_id}",
            details={
                "transfer_job_id": str(transfer_job_id),
                "question_id": str(question_id),
            },
        )


class SameConfigurationError(ValidationError, TransferError):
    """Raised when the source and the target of a transfer are one configuration."""

    code = "same_configuration"

    def __init__(self, configuration_id: object) -> None:
        super().__init__(
            "the source and the target configuration must differ",
            details={"chunking_configuration_id": str(configuration_id)},
        )


class NothingToTransferError(ValidationError, TransferError):
    """Raised when no question of the set is left to propose chunks for.

    Questions already decided in the target are never proposed again, since a job must not
    put a human decision back into question; with a source, only questions confirmed there
    have something to transfer.
    """

    code = "nothing_to_transfer"

    def __init__(self, skipped: dict[str, int]) -> None:
        super().__init__(
            "no question is left to propose chunks for",
            details={"skipped": skipped},
        )


class UncoveredQuestionsChoiceRequiredError(ValidationError, TransferError):
    """Raised when some questions cannot be ranked because their documents have no chunks.

    The candidates of a question are the chunks of its gold documents in the target
    configuration: a document not materialised there has none, and the question would look
    like it has no evidence when it was never searched. The caller excludes them
    explicitly, or materialises the configuration on those documents first.
    """

    code = "uncovered_questions_choice_required"

    def __init__(self, uncovered: list[dict[str, Any]]) -> None:
        super().__init__(
            f"{len(uncovered)} question(s) have gold documents without chunks in the target "
            "configuration: exclude them (exclude_uncovered=true) or materialise it first",
            details={"uncovered_questions": uncovered},
        )


class TransferNotCancellableError(ConflictError, TransferError):
    """Raised when cancelling a job that already ended."""

    code = "transfer_not_cancellable"

    def __init__(self, transfer_job_id: object, status: object) -> None:
        super().__init__(
            f"transfer job {transfer_job_id} is not running (status={status})",
            details={"transfer_job_id": str(transfer_job_id), "status": str(status)},
        )


class TransferNotResumableError(ConflictError, TransferError):
    """Raised when resuming a job that is running or has nothing left to rank."""

    code = "transfer_not_resumable"

    def __init__(self, transfer_job_id: object, reason: str) -> None:
        super().__init__(
            f"transfer job {transfer_job_id} cannot be resumed: {reason}",
            details={"transfer_job_id": str(transfer_job_id), "reason": reason},
        )
