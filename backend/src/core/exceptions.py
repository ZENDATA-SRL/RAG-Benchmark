from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base class for every error the domain raises deliberately.

    Carrying `code` and `status_code` on the exception is what lets a single handler in
    `create_app` serialise all of them: the service layer never imports FastAPI and the
    routers never translate errors by hand.

    Attributes:
        code: Stable machine-readable identifier, e.g. `documents_not_in_corpus`. The UI
            branches on this and not on the message, which is free to change.
        status_code: HTTP status the handler responds with.
        details: Extra context, e.g. the offending field path.
    """

    code: str = "domain_error"
    status_code: int = 400

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(DomainError):
    """A referenced entity does not exist."""

    code = "not_found"
    status_code = 404


class ConflictError(DomainError):
    """The request contradicts the current state of a resource."""

    code = "conflict"
    status_code = 409


class ValidationError(DomainError):
    """The payload is well-formed but violates a domain rule."""

    code = "validation_error"
    status_code = 422


class UnsupportedOperationError(DomainError):
    """The operation is modelled but not implemented in this version."""

    code = "unsupported_operation"
    status_code = 422
