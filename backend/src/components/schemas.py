from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.infrastructure.database.enums import ComponentType, RuntimeType


class ComponentVersionRead(BaseModel):
    """A component version as exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    component_id: uuid.UUID
    version: str
    runtime: RuntimeType
    endpoint: str | None = None
    params_schema: dict[str, Any]
    capabilities: dict[str, Any]
    is_available: bool
    unavailable_reason: str | None = None
    created_at: dt.datetime


class ComponentRead(BaseModel):
    """A component as exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: ComponentType
    key: str
    display_name: str
    created_at: dt.datetime


class ComponentWithVersionsRead(ComponentRead):
    """A component together with its versions, so the UI builds its forms in one call (RT-U01)."""

    versions: list[ComponentVersionRead] = Field(default_factory=list)


class ComponentCreate(BaseModel):
    """Payload registering a component."""

    type: ComponentType
    key: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)


class ComponentVersionCreate(BaseModel):
    """Payload registering a version of a component."""

    version: str = Field(min_length=1, max_length=50)
    runtime: RuntimeType = RuntimeType.BUILTIN
    endpoint: str | None = None
    params_schema: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)


class ComponentVersionUnavailable(BaseModel):
    """Payload excluding a version from the available choices."""

    reason: str = Field(min_length=1, max_length=500)


class ErrorResponse(BaseModel):
    """Uniform error body returned for every domain error."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
