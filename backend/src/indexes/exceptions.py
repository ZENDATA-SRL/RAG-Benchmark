from __future__ import annotations

from src.core.exceptions import (
    DomainError,
    NotFoundError,
)


class IndexBuildError(DomainError):
    """Base class for index build errors."""

    code = "index_build_error"


class IndexBuildNotFoundError(NotFoundError, IndexBuildError):
    """Raised when a referenced index build does not exist."""

    code = "index_build_not_found"

    def __init__(self, index_build_id: object) -> None:
        super().__init__(
            f"index build not found: {index_build_id}",
            details={"index_build_id": str(index_build_id)},
        )
        self.index_build_id = index_build_id
