from __future__ import annotations

from src.core.exceptions import DomainError, NotFoundError


class SourceError(DomainError):
    """Base class for source and import domain errors."""

    code = "source_error"


class SourceConnectionNotFoundError(NotFoundError, SourceError):
    """Raised when a connection does not exist."""

    code = "source_connection_not_found"

    def __init__(self, connection_id: object) -> None:
        super().__init__(
            f"source connection not found: {connection_id}",
            details={"connection_id": str(connection_id)},
        )
        self.connection_id = connection_id


class ImportRunNotFoundError(NotFoundError, SourceError):
    """Raised when an import run does not exist."""

    code = "import_run_not_found"

    def __init__(self, import_run_id: object) -> None:
        super().__init__(
            f"import run not found: {import_run_id}",
            details={"import_run_id": str(import_run_id)},
        )
        self.import_run_id = import_run_id
