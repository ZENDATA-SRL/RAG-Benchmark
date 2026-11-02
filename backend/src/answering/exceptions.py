from __future__ import annotations

from src.core.exceptions import DomainError


class AnsweringError(DomainError):
    """Base class for the errors of an answer system."""

    code = "answering_error"


class AnswerOutputError(AnsweringError):
    """Raised when the model answered, but not in the declared shape.

    Permanent for the question: asking again with the same prompt and model is expected to
    fail the same way, so the execution fails instead of being retried.
    """

    code = "answer_output_error"

    def __init__(self, reason: str) -> None:
        super().__init__(f"answer not in the expected shape: {reason}")
        self.reason = reason


class AnswerProviderError(AnsweringError):
    """Raised when the model provider failed: network, rate limit, server error.

    Transient: the workflow retries it with backoff. Reported as a bad gateway, like a
    failure of the embedder or the vector store.
    """

    code = "answer_provider_error"
    status_code = 502

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(
            f"{provider} failed: {reason}",
            details={"provider": provider, "reason": reason},
        )
        self.provider = provider
        self.reason = reason


class AnswerSystemUnavailableError(AnsweringError):
    """Raised when the provider a profile names cannot be used by this worker.

    Permanent: a missing credential does not appear by retrying.
    """

    code = "answer_system_unavailable"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
