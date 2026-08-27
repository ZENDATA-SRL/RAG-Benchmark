from __future__ import annotations


class PipelineError(Exception):
    """Base class for pipeline domain errors."""


class ProfileNotFoundError(PipelineError):
    """Raised when a referenced profile does not exist."""

    def __init__(self, kind: str, profile_id: object) -> None:
        super().__init__(f"{kind} profile not found: {profile_id}")
        self.kind = kind
        self.profile_id = profile_id


class UnsupportedChunkerScopeError(PipelineError):
    """Raised when a chunking profile declares a scope other than `document`.

    Per-document materialisation is what keeps the chunk-level gold valid across changes
    of corpus composition (RF-P10), so a corpus-scoped chunker cannot be cached per
    document and is out of scope for v1 (RF-R03).
    """

    def __init__(self, scope: str) -> None:
        super().__init__(f"chunker scope not supported in v1: {scope!r} (expected 'document')")
        self.scope = scope


class ParsingResultNotReadyError(PipelineError):
    """Raised when chunking is requested from a parse that has not succeeded."""

    def __init__(self, parsing_result_id: object, status: object) -> None:
        super().__init__(f"parsing result {parsing_result_id} is not ready (status={status})")
        self.parsing_result_id = parsing_result_id
        self.status = status


class ParsingProfileMismatchError(PipelineError):
    """Raised when a parse does not belong to the configuration's parsing profile.

    The database enforces this with a composite foreign key; this error exists so the
    caller gets a readable message instead of an integrity violation.
    """

    def __init__(self, expected: object, actual: object) -> None:
        super().__init__(
            f"parse belongs to parsing profile {actual}, configuration expects {expected}"
        )
        self.expected = expected
        self.actual = actual
