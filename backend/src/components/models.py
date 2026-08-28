from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from src.infrastructure.database.enums import (
    COMPONENT_TYPE,
    RUNTIME_TYPE,
    ComponentType,
    RuntimeType,
)


class Component(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Logical identity of a pluggable component: type + key, e.g. `parser/azure_di`.

    Registrable without code changes.
    """

    __tablename__ = "components"
    __table_args__ = (UniqueConstraint("type", "key"),)

    type: Mapped[ComponentType] = mapped_column(COMPONENT_TYPE, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)

    versions: Mapped[list[ComponentVersion]] = relationship(
        back_populates="component", cascade="all, delete-orphan"
    )


class ComponentVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A concrete implementation of a component; several versions stay active at once.

    `params_schema` is the JSON Schema the UI renders a form from;
    `capabilities` declares supported modalities, formats, citation support and — for
    chunkers — the processing scope, which in v1 may only be `document`.
    """

    __tablename__ = "component_versions"
    __table_args__ = (UniqueConstraint("component_id", "version"),)

    component_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[str] = mapped_column(Text, nullable=False)
    runtime: Mapped[RuntimeType] = mapped_column(RUNTIME_TYPE, nullable=False)
    endpoint: Mapped[str | None] = mapped_column(Text)
    params_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )
    capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )
    is_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    unavailable_reason: Mapped[str | None] = mapped_column(Text)

    component: Mapped[Component] = relationship(back_populates="versions")
