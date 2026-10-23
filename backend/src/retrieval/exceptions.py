from __future__ import annotations

from src.core.exceptions import ConflictError, DomainError


class RetrievalError(DomainError):
    """Base class for retrieval errors."""

    code = "retrieval_error"


class IndexBuildNotReadyError(ConflictError, RetrievalError):
    """Raised when a query targets an index build that has not finished.

    A half-built index would answer differently depending on when it was asked, so it is
    refused instead of queried.
    """

    code = "index_build_not_ready"

    def __init__(self, index_build_id: object, status: str) -> None:
        super().__init__(
            f"index build {index_build_id} is {status}, not ready",
            details={"index_build_id": str(index_build_id), "status": status},
        )
        self.index_build_id = index_build_id
        self.status = status


class RetrievalBackendError(RetrievalError):
    """Raised when the embedder or the vector store fails to answer a query.

    Reported as a bad gateway: the request was valid, a dependency of the API was not.
    `stage` tells which one, so a missing credential is not mistaken for a down server.
    """

    code = "retrieval_backend_error"
    status_code = 502

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(
            f"{stage} failed: {reason}", details={"stage": stage, "reason": reason}
        )
        self.stage = stage
        self.reason = reason
