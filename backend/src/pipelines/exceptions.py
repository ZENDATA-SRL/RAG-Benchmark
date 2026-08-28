from __future__ import annotations

from src.core.exceptions import (
    DomainError,
    NotFoundError,
    UnsupportedOperationError,
    ValidationError,
)


class PipelineError(DomainError):
    """Base class for pipeline domain errors."""

    code = "pipeline_error"


class ProfileNotFoundError(NotFoundError, PipelineError):
    """Raised when a referenced profile does not exist."""

    code = "profile_not_found"

    def __init__(self, kind: str, profile_id: object) -> None:
        super().__init__(
            f"{kind} profile not found: {profile_id}",
            details={"kind": kind, "profile_id": str(profile_id)},
        )
        self.kind = kind
        self.profile_id = profile_id


class UnsupportedChunkerScopeError(UnsupportedOperationError, PipelineError):
    """Raised when a chunking profile declares a scope other than `document`.

    Per-document materialisation is what keeps the chunk-level gold valid across changes
    of corpus composition, so a corpus-scoped chunker cannot be cached per
    document and is out of scope for v1.
    """

    code = "unsupported_chunker_scope"

    def __init__(self, scope: str) -> None:
        super().__init__(
            f"chunker scope not supported in v1: {scope!r} (expected 'document')",
            details={"scope": scope, "expected": "document"},
        )
        self.scope = scope


class ParsingResultNotReadyError(ValidationError, PipelineError):
    """Raised when chunking is requested from a parse that has not succeeded."""

    code = "parsing_result_not_ready"

    def __init__(self, parsing_result_id: object, status: object) -> None:
        super().__init__(
            f"parsing result {parsing_result_id} is not ready (status={status})",
            details={"parsing_result_id": str(parsing_result_id), "status": str(status)},
        )
        self.parsing_result_id = parsing_result_id
        self.status = status


class ParsingProfileMismatchError(ValidationError, PipelineError):
    """Raised when a parse does not belong to the configuration's parsing profile.

    The database enforces this with a composite foreign key; this error exists so the
    caller gets a readable message instead of an integrity violation.
    """

    code = "parsing_profile_mismatch"

    def __init__(self, expected: object, actual: object) -> None:
        super().__init__(
            f"parse belongs to parsing profile {actual}, configuration expects {expected}",
            details={"expected": str(expected), "actual": str(actual)},
        )
        self.expected = expected
        self.actual = actual
