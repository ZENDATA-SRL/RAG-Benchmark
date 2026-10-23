from __future__ import annotations

from src.core.exceptions import (
    DomainError,
    NotFoundError,
    UnsupportedOperationError,
)


class PipelineError(DomainError):
    """Base class for errors on pipeline profiles and chunking configurations."""

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


class UnsupportedRetrievalFeatureError(UnsupportedOperationError, PipelineError):
    """Raised when a retrieval profile asks for something the engine does not apply yet."""

    code = "unsupported_retrieval_feature"

    def __init__(self, field: str, value: object) -> None:
        super().__init__(
            f"retrieval {field} not available yet: {value!r}; only dense retrieval "
            "is supported",
            details={"field": field, "value": str(value)},
        )
        self.field = field
        self.value = value


class ChunkingConfigurationNotFoundError(NotFoundError, PipelineError):
    """Raised when a referenced chunking configuration does not exist."""

    code = "chunking_configuration_not_found"

    def __init__(self, configuration_id: object) -> None:
        super().__init__(
            f"chunking configuration not found: {configuration_id}",
            details={"chunking_configuration_id": str(configuration_id)},
        )
        self.configuration_id = configuration_id
