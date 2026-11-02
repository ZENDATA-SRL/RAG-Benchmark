from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class AnswerProfile(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """An answer system and the parameters it is run with: model, prompt, temperature.

    Content-addressed like the pipeline profiles: the hash covers the component version and
    the parameters, so the same configuration asked for twice is one row. The parent is
    the profile this one was derived from, kept to show what changed.
    """

    __tablename__ = "answer_profiles"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    component_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )
    config_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    parent_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("answer_profiles.id", ondelete="SET NULL"),
    )
