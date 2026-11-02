from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.pipelines.schemas import DeduplicatedRead


class AnswerProfileCreate(BaseModel):
    """Payload creating an answer profile; the name is derived by the server."""

    component_version_id: uuid.UUID
    params: dict[str, Any] = Field(default_factory=dict)
    parent_profile_id: uuid.UUID | None = None


class AnswerProfileRead(BaseModel):
    """An answer profile as exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    component_version_id: uuid.UUID
    params: dict[str, Any] = Field(default_factory=dict)
    config_hash: str
    parent_profile_id: uuid.UUID | None = None
    created_at: dt.datetime


class ParamChangeRead(BaseModel):
    """A parameter whose value differs from the parent profile's."""

    key: str
    parent: Any = None
    value: Any = None


class AnswerProfileDetail(AnswerProfileRead):
    """A profile with what changed from the profile it was derived from."""

    changed_params: list[ParamChangeRead] = Field(default_factory=list)


class AnswerProfileCreated(DeduplicatedRead):
    """An answer profile with the outcome of the get-or-create that returned it."""

    profile: AnswerProfileRead
