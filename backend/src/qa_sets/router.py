from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile, status

from src.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from src.dependencies import SessionDep
from src.qa_sets.constants import QA_SNAPSHOT_REUSED_DETAIL
from src.qa_sets.schemas import (
    ImportSummaryRead,
    QASetCreate,
    QASetDetail,
    QASetRead,
    QASetSnapshotCreate,
    QASetSnapshotCreated,
    QASetSnapshotRead,
    QuestionRead,
)
from src.qa_sets.service import QASetService, QASetSnapshotService

router = APIRouter(prefix="/qa-sets", tags=["qa-sets"])


@router.post("", response_model=QASetRead, status_code=status.HTTP_201_CREATED)
async def create_qa_set(payload: QASetCreate, session: SessionDep) -> QASetRead:
    """Create an empty QA set."""
    qa_set = await QASetService(session).create(
        payload.name, payload.description, payload.origin_corpus_id
    )
    return QASetRead.model_validate(qa_set)


@router.get("", response_model=Page[QASetRead])
async def list_qa_sets(
    session: SessionDep,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[QASetRead]:
    """List the QA sets with their question counts."""
    qa_sets, counts, total = await QASetService(session).list(
        limit=limit, offset=offset
    )
    items = []
    for qa_set in qa_sets:
        item = QASetRead.model_validate(qa_set)
        item.question_count = counts.get(qa_set.id, 0)
        items.append(item)
    return Page[QASetRead].build(items, total=total, limit=limit, offset=offset)


@router.get("/{qa_set_id}", response_model=QASetDetail)
async def get_qa_set(
    qa_set_id: uuid.UUID,
    session: SessionDep,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> QASetDetail:
    """Return a QA set with a page of its questions and their gold documents."""
    service = QASetService(session)
    qa_set = await service.get(qa_set_id)
    questions, total = await service.list_questions(
        qa_set_id, limit=limit, offset=offset
    )
    return QASetDetail(
        **QASetRead.model_validate(qa_set).model_dump(exclude={"question_count"}),
        question_count=total,
        questions=Page[QuestionRead].build(
            [QuestionRead.model_validate(question) for question in questions],
            total=total,
            limit=limit,
            offset=offset,
        ),
    )


@router.post("/{qa_set_id}/import", response_model=ImportSummaryRead)
async def import_questions(
    qa_set_id: uuid.UUID, session: SessionDep, file: Annotated[UploadFile, File()]
) -> ImportSummaryRead:
    """Import questions and gold files from a CSV or JSONL file, reporting every row."""
    summary = await QASetService(session).import_file(
        qa_set_id, file.filename or "", await file.read()
    )
    return ImportSummaryRead.model_validate(summary)


@router.post(
    "/{qa_set_id}/snapshots",
    response_model=QASetSnapshotCreated,
    status_code=status.HTTP_201_CREATED,
)
async def freeze_qa_set(
    qa_set_id: uuid.UUID, payload: QASetSnapshotCreate, session: SessionDep
) -> QASetSnapshotCreated:
    """Freeze the current questions, or return the snapshot with the same composition."""
    snapshot, created = await QASetSnapshotService(session).get_or_create_reporting(
        qa_set_id, label=payload.label
    )
    return QASetSnapshotCreated(
        snapshot=QASetSnapshotRead.model_validate(snapshot),
        created=created,
        detail=None if created else QA_SNAPSHOT_REUSED_DETAIL,
    )


@router.get("/{qa_set_id}/snapshots", response_model=Page[QASetSnapshotRead])
async def list_qa_set_snapshots(
    qa_set_id: uuid.UUID,
    session: SessionDep,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[QASetSnapshotRead]:
    """List the snapshots of a QA set, newest first."""
    snapshots, total = await QASetSnapshotService(session).list(
        qa_set_id, limit=limit, offset=offset
    )
    return Page[QASetSnapshotRead].build(
        [QASetSnapshotRead.model_validate(snapshot) for snapshot in snapshots],
        total=total,
        limit=limit,
        offset=offset,
    )
