from __future__ import annotations

from src.core.exceptions import DomainError, NotFoundError, ValidationError


class DocumentError(DomainError):
    """Base class for document domain errors."""

    code = "document_error"


class DocumentNotFoundError(NotFoundError, DocumentError):
    """Raised when a document does not exist."""

    code = "document_not_found"

    def __init__(self, document_id: object) -> None:
        super().__init__(
            f"document not found: {document_id}",
            details={"document_id": str(document_id)},
        )
        self.document_id = document_id


class UnsupportedMimeTypeError(ValidationError, DocumentError):
    """Raised when a file's MIME type is not accepted by this deployment.

    Carries the allowed list because the caller cannot otherwise know what to send, and
    the set is configuration rather than a property of the build.
    """

    code = "unsupported_mime_type"

    def __init__(self, mime_type: str, allowed: tuple[str, ...]) -> None:
        super().__init__(
            f"unsupported mime type: {mime_type} (allowed: {', '.join(allowed)})",
            details={"mime_type": mime_type, "allowed": list(allowed)},
        )
        self.mime_type = mime_type
        self.allowed = allowed


class FileTooLargeError(ValidationError, DocumentError):
    """Raised when a file exceeds `max_upload_bytes`."""

    code = "file_too_large"

    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        super().__init__(
            f"file too large: {size_bytes} bytes (max {max_bytes})",
            details={"size_bytes": size_bytes, "max_bytes": max_bytes},
        )
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes


class EmptyFileError(ValidationError, DocumentError):
    """Raised when an uploaded file has no content.

    Rejected explicitly because every empty file shares one sha-256: accepting them would
    collapse unrelated uploads onto a single deduplicated document.
    """

    code = "empty_file"

    def __init__(self, filename: str) -> None:
        super().__init__(
            f"file is empty: {filename}",
            details={"filename": filename},
        )
        self.filename = filename


class DocumentContentUnavailableError(DocumentError):
    """Raised when a document row exists but its bytes are not readable yet."""

    code = "document_content_unavailable"
    status_code = 409

    def __init__(self, document_id: object, status: object) -> None:
        status_name = getattr(status, "value", status)
        super().__init__(
            f"document {document_id} has no readable content (status: {status_name})",
            details={"document_id": str(document_id), "status": str(status_name)},
        )
        self.document_id = document_id
        self.status = status
