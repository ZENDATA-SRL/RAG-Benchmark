from __future__ import annotations

from src.core.exceptions import (
    ConflictError,
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


class ChunkingConfigurationNotFoundError(NotFoundError, PipelineError):
    """Raised when a referenced chunking configuration does not exist."""

    code = "chunking_configuration_not_found"

    def __init__(self, configuration_id: object) -> None:
        super().__init__(
            f"chunking configuration not found: {configuration_id}",
            details={"chunking_configuration_id": str(configuration_id)},
        )
        self.configuration_id = configuration_id


class IndexBuildNotFoundError(NotFoundError, PipelineError):
    """Raised when a referenced index build does not exist."""

    code = "index_build_not_found"

    def __init__(self, index_build_id: object) -> None:
        super().__init__(
            f"index build not found: {index_build_id}",
            details={"index_build_id": str(index_build_id)},
        )
        self.index_build_id = index_build_id


class MaterializationRunNotFoundError(NotFoundError, PipelineError):
    """Raised when a referenced materialisation run does not exist."""

    code = "materialization_run_not_found"

    def __init__(self, run_id: object) -> None:
        super().__init__(
            f"materialization run not found: {run_id}",
            details={"materialization_run_id": str(run_id)},
        )
        self.run_id = run_id


class ChunkNotFoundError(NotFoundError, PipelineError):
    """Raised when a chunk id does not exist."""

    code = "chunk_not_found"

    def __init__(self, chunk_id: object) -> None:
        super().__init__(
            f"chunk not found: {chunk_id}", details={"chunk_id": str(chunk_id)}
        )
        self.chunk_id = chunk_id


class ChunkResultNotFoundError(NotFoundError, PipelineError):
    """Raised when a document has no chunk result under a configuration.

    Distinct from an empty chunk list on purpose: "never materialised" and "materialised
    into zero chunks" are different answers, and the UI has to be able to tell them apart.
    """

    code = "chunk_result_not_found"

    def __init__(self, document_id: object, chunking_configuration_id: object) -> None:
        super().__init__(
            f"document {document_id} has no chunk result for configuration "
            f"{chunking_configuration_id}",
            details={
                "document_id": str(document_id),
                "chunking_configuration_id": str(chunking_configuration_id),
            },
        )
        self.document_id = document_id
        self.chunking_configuration_id = chunking_configuration_id


class ParsingResultNotFoundError(NotFoundError, PipelineError):
    """Raised when a document has no parse under a parsing profile."""

    code = "parsing_result_not_found"

    def __init__(self, document_id: object, parsing_profile_id: object) -> None:
        super().__init__(
            f"document {document_id} has no parse for profile {parsing_profile_id}",
            details={
                "document_id": str(document_id),
                "parsing_profile_id": str(parsing_profile_id),
            },
        )
        self.document_id = document_id
        self.parsing_profile_id = parsing_profile_id


class DocumentsNotStoredError(ValidationError, PipelineError):
    """Raised when a materialisation is requested on documents that are not `stored`.

    Names the offending documents rather than only the count: a user who selected fifty
    files needs to know which of them to fix.
    """

    code = "documents_not_stored"

    def __init__(self, offending: dict[str, str]) -> None:
        listed = ", ".join(f"{doc_id} ({status})" for doc_id, status in offending.items())
        super().__init__(
            f"materialisation needs every document to be stored; not stored: {listed}",
            details={"documents": offending, "expected_status": "stored"},
        )
        self.offending = offending


class EmptyMaterializationError(ValidationError, PipelineError):
    """Raised when a materialisation would run on no document at all.

    Refused instead of launching an empty workflow, because the deterministic id of an empty
    document set is the same for every configuration and would silently collide.
    """

    code = "empty_materialization"

    def __init__(self) -> None:
        super().__init__("a materialisation needs at least one document")


class MaterializationNotCancellableError(ConflictError, PipelineError):
    """Raised when cancellation is requested on a run that already finished."""

    code = "materialization_not_cancellable"

    def __init__(self, run_id: object, status: object) -> None:
        super().__init__(
            f"materialization run {run_id} is not running (status={status})",
            details={"materialization_run_id": str(run_id), "status": str(status)},
        )
        self.run_id = run_id
        self.status = status


class InvalidConfigurationListError(ValidationError, PipelineError):
    """Raised when the comma-separated list of configurations to compare is malformed."""

    code = "invalid_configuration_list"

    def __init__(self, raw: str) -> None:
        super().__init__(
            f"expected a comma-separated list of configuration ids, got {raw!r}",
            details={"configurations": raw},
        )
        self.raw = raw
