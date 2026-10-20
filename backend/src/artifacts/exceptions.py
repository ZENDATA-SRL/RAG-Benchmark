from __future__ import annotations

from src.core.exceptions import (
    DomainError,
    NotFoundError,
    ValidationError,
)


class ArtifactError(DomainError):
    """Base class for errors on per-document parsing and chunking artefacts."""

    code = "artifact_error"


class ParsingResultNotReadyError(ValidationError, ArtifactError):
    """Raised when chunking is requested from a parse that has not succeeded."""

    code = "parsing_result_not_ready"

    def __init__(self, parsing_result_id: object, status: object) -> None:
        super().__init__(
            f"parsing result {parsing_result_id} is not ready (status={status})",
            details={
                "parsing_result_id": str(parsing_result_id),
                "status": str(status),
            },
        )
        self.parsing_result_id = parsing_result_id
        self.status = status


class ParsingProfileMismatchError(ValidationError, ArtifactError):
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


class ChunkNotFoundError(NotFoundError, ArtifactError):
    """Raised when a chunk id does not exist."""

    code = "chunk_not_found"

    def __init__(self, chunk_id: object) -> None:
        super().__init__(
            f"chunk not found: {chunk_id}", details={"chunk_id": str(chunk_id)}
        )
        self.chunk_id = chunk_id


class ChunkResultNotFoundError(NotFoundError, ArtifactError):
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


class ParsingResultNotFoundError(NotFoundError, ArtifactError):
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


class InvalidConfigurationListError(ValidationError, ArtifactError):
    """Raised when the comma-separated list of configurations to compare is malformed."""

    code = "invalid_configuration_list"

    def __init__(self, raw: str) -> None:
        super().__init__(
            f"expected a comma-separated list of configuration ids, got {raw!r}",
            details={"configurations": raw},
        )
        self.raw = raw
