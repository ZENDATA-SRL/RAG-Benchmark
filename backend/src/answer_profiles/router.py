from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from src.answer_profiles.schemas import (
    AnswerProfileCreate,
    AnswerProfileCreated,
    AnswerProfileDetail,
    AnswerProfileRead,
    ParamChangeRead,
)
from src.answer_profiles.service import AnswerProfileService
from src.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from src.dependencies import SessionDep
from src.pipelines.constants import REUSED_DETAIL

router = APIRouter(prefix="/answer-profiles", tags=["answer-profiles"])


@router.post(
    "", response_model=AnswerProfileCreated, status_code=status.HTTP_201_CREATED
)
async def create_answer_profile(
    payload: AnswerProfileCreate, session: SessionDep
) -> AnswerProfileCreated:
    """Create an answer profile, or return the identical one that already exists."""
    profile, created = await AnswerProfileService(session).get_or_create(
        component_version_id=payload.component_version_id,
        params=payload.params,
        parent_profile_id=payload.parent_profile_id,
    )
    return AnswerProfileCreated(
        profile=AnswerProfileRead.model_validate(profile),
        created=created,
        detail=None if created else REUSED_DETAIL,
    )


@router.get("", response_model=Page[AnswerProfileRead])
async def list_answer_profiles(
    session: SessionDep,
    component_version_id: uuid.UUID | None = None,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[AnswerProfileRead]:
    """List the answer profiles, optionally of one answer system version."""
    profiles, total = await AnswerProfileService(session).list(
        component_version_id=component_version_id, limit=limit, offset=offset
    )
    return Page[AnswerProfileRead].build(
        [AnswerProfileRead.model_validate(profile) for profile in profiles],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{profile_id}", response_model=AnswerProfileDetail)
async def get_answer_profile(
    profile_id: uuid.UUID, session: SessionDep
) -> AnswerProfileDetail:
    """Return one answer profile with the parameters changed from its parent."""
    service = AnswerProfileService(session)
    profile = await service.get(profile_id)
    return AnswerProfileDetail(
        **AnswerProfileRead.model_validate(profile).model_dump(),
        changed_params=[
            ParamChangeRead(key=key, parent=parent, value=value)
            for key, parent, value in await service.changed_params(profile)
        ],
    )
