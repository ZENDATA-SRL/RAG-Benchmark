from __future__ import annotations

from typing import Any

from src.core.exceptions import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)


class GenerationError(DomainError):
    """Base class for question generation errors."""

    code = "generation_error"


class GenerationJobNotFoundError(NotFoundError, GenerationError):
    """Raised when a generation job does not exist."""

    code = "generation_job_not_found"

    def __init__(self, generation_job_id: object) -> None:
        super().__init__(
            f"generation job not found: {generation_job_id}",
            details={"generation_job_id": str(generation_job_id)},
        )


class GenerationUnitNotFoundError(NotFoundError, GenerationError):
    """Raised when a unit of a generation job does not exist."""

    code = "generation_unit_not_found"

    def __init__(self, unit_id: object) -> None:
        super().__init__(
            f"generation unit not found: {unit_id}",
            details={"unit_id": str(unit_id)},
        )


class ProposalNotFoundError(NotFoundError, GenerationError):
    """Raised when a generated question does not exist."""

    code = "generated_question_not_found"

    def __init__(self, proposal_id: object) -> None:
        super().__init__(
            f"generated question not found: {proposal_id}",
            details={"generated_question_id": str(proposal_id)},
        )


class QASetWithoutCorpusError(ValidationError, GenerationError):
    """Raised when generating for a set that has no origin corpus.

    The documents a job reads are the corpus where the set's questions are written; a set
    without one has nothing to read from.
    """

    code = "qa_set_without_corpus"

    def __init__(self, qa_set_id: object) -> None:
        super().__init__(
            "the QA set has no origin corpus to generate questions from",
            details={"qa_set_id": str(qa_set_id)},
        )


class NothingToGenerateError(ValidationError, GenerationError):
    """Raised when a job would generate nothing: no question asked, or no document left."""

    code = "nothing_to_generate"

    def __init__(self, reason: str) -> None:
        super().__init__(reason, details={"reason": reason})


class DocumentsOutsideCorpusError(ValidationError, GenerationError):
    """Raised when the documents chosen for a job are not documents of the set's corpus."""

    code = "documents_outside_corpus"

    def __init__(self, document_ids: list[object]) -> None:
        super().__init__(
            f"{len(document_ids)} document(s) are not in the QA set's origin corpus",
            details={"document_ids": [str(item) for item in document_ids]},
        )


class CrossNeedsDocumentsError(ValidationError, GenerationError):
    """Raised when cross-document questions are asked of fewer than two documents."""

    code = "cross_needs_two_documents"

    def __init__(self, documents: int) -> None:
        super().__init__(
            "questions across documents need at least two documents",
            details={"documents": documents},
        )


class UnmaterializedDocumentsChoiceRequiredError(ValidationError, GenerationError):
    """Raised when some documents of the corpus cannot be read under the configuration.

    A document without ready chunks there, or whose parse kept no text, gives the agent
    nothing to read or cite. Silently skipping it would make the corpus look covered when
    it was not, so the caller excludes those documents explicitly or materialises the
    configuration on them first.
    """

    code = "unmaterialized_documents_choice_required"

    def __init__(self, documents: list[dict[str, Any]]) -> None:
        super().__init__(
            f"{len(documents)} document(s) have no chunks or text in the configuration: "
            "exclude them (exclude_unmaterialized=true) or materialise it first",
            details={"unmaterialized_documents": documents},
        )


class ChunksOutsideJobError(ValidationError, GenerationError):
    """Raised when an accepted question cites chunks the job could not read."""

    code = "chunks_outside_job"

    def __init__(self, chunk_ids: list[object]) -> None:
        super().__init__(
            f"{len(chunk_ids)} chunk(s) are not chunks of the job's documents in its "
            "configuration",
            details={"chunk_ids": [str(item) for item in chunk_ids]},
        )


class ProposalAlreadyReviewedError(ConflictError, GenerationError):
    """Raised when deciding on a generated question that was already decided."""

    code = "generated_question_already_reviewed"

    def __init__(self, proposal_id: object, status: object) -> None:
        super().__init__(
            f"generated question {proposal_id} was already {status}",
            details={"generated_question_id": str(proposal_id), "status": str(status)},
        )


class GenerationNotCancellableError(ConflictError, GenerationError):
    """Raised when cancelling a job that already ended."""

    code = "generation_not_cancellable"

    def __init__(self, generation_job_id: object, status: object) -> None:
        super().__init__(
            f"generation job {generation_job_id} is not running (status={status})",
            details={
                "generation_job_id": str(generation_job_id),
                "status": str(status),
            },
        )


class GenerationNotResumableError(ConflictError, GenerationError):
    """Raised when resuming a job that is running or has no unit left to run."""

    code = "generation_not_resumable"

    def __init__(self, generation_job_id: object, reason: str) -> None:
        super().__init__(
            f"generation job {generation_job_id} cannot be resumed: {reason}",
            details={"generation_job_id": str(generation_job_id), "reason": reason},
        )


class GenerationProviderError(GenerationError):
    """Raised when the model provider failed: network, rate limit, server error.

    Transient: the workflow retries the unit with backoff, and the unit starts again from
    what is left of its target.
    """

    code = "generation_provider_error"
    status_code = 502

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(
            f"{provider} failed: {reason}",
            details={"provider": provider, "reason": reason},
        )
