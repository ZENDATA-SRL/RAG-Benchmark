from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum


class SourceType(str, enum.Enum):
    UPLOAD = "upload"
    FILESYSTEM = "filesystem"
    S3 = "s3"
    SHAREPOINT = "sharepoint"
    CONFLUENCE = "confluence"


class AuthMethod(str, enum.Enum):
    NONE = "none"
    API_KEY = "api_key"
    TOKEN = "token"
    BASIC = "basic"
    OAUTH2 = "oauth2"


class ImportStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


class FileOutcome(str, enum.Enum):
    IMPORTED = "imported"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_UNSUPPORTED = "skipped_unsupported"
    FAILED = "failed"


class DocumentStatus(str, enum.Enum):
    """Lifecycle of a file *acquisition*: fetched, hashed, stored."""

    PENDING = "pending"
    FETCHING = "fetching"
    STORED = "stored"
    FAILED = "failed"


class ArtifactStatus(str, enum.Enum):
    """Lifecycle of a *pipeline artefact*, shared by parsing, chunking and index builds."""

    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


# A run or artefact that reached one of these is over: relaunching the same work reopens
# the row, and cancelling it is refused.
TERMINAL_ARTIFACT_STATUSES = (ArtifactStatus.READY, ArtifactStatus.FAILED)


class ComponentType(str, enum.Enum):
    SOURCE = "source"
    PARSER = "parser"
    CHUNKER = "chunker"
    EMBEDDER = "embedder"
    VECTOR_STORE = "vector_store"
    RERANKER = "reranker"
    ANSWER_SYSTEM = "answer_system"
    JUDGE = "judge"


class RuntimeType(str, enum.Enum):
    BUILTIN = "builtin"
    HTTP = "http"


def pg_enum(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    """Build a native PostgreSQL ENUM that stores the enum *values*.

    Args:
        enum_cls: Python enum class to map.
        name: Name of the PostgreSQL type.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        create_type=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


# Reused singletons: sharing one instance per PostgreSQL type avoids duplicated
# CREATE TYPE statements when the same enum is used by several tables.
SOURCE_TYPE = pg_enum(SourceType, "source_type")
AUTH_METHOD = pg_enum(AuthMethod, "auth_method")
IMPORT_STATUS = pg_enum(ImportStatus, "import_status")
FILE_OUTCOME = pg_enum(FileOutcome, "file_outcome")
DOCUMENT_STATUS = pg_enum(DocumentStatus, "document_status")
ARTIFACT_STATUS = pg_enum(ArtifactStatus, "artifact_status")
COMPONENT_TYPE = pg_enum(ComponentType, "component_type")
RUNTIME_TYPE = pg_enum(RuntimeType, "runtime_type")
