from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from src.infrastructure.database.enums import ARTIFACT_STATUS, ArtifactStatus


class MaterializationRun(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The denormalised record of one user-triggered chunk materialisation.

    `chunk_results` alone cannot answer "which request produced these, and how many are
    still pending": this row does, so the UI shows progress without polling
    Temporal on every refresh. The authoritative state stays in Temporal; this is a copy
    kept fresh by the run's activities, exactly as `import_runs` and `index_builds` do.

    The per-document outcome is deliberately *not* duplicated here: it belongs to the
    artefact (`chunk_results.error`), the way `import_file_results` holds it for an import.
    `error` carries only what is a property of the run itself, i.e. why it ended the way it
    did when that is not visible from the artefacts — a cancellation.
    """

    __tablename__ = "materialization_runs"

    chunking_configuration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunking_configurations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    corpus_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpora.id", ondelete="SET NULL"),
        index=True,
    )
    workflow_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[ArtifactStatus] = mapped_column(
        ARTIFACT_STATUS, nullable=False, server_default=ArtifactStatus.PENDING.value
    )
    document_count: Mapped[int] = mapped_column(Integer, nullable=False)
    progress: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
