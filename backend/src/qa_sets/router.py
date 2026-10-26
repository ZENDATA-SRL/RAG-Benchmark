from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile, status

from src.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from src.dependencies import SessionDep
from src.qa_sets.constants import QA_SNAPSHOT_REUSED_DETAIL
from src.qa_sets.evidence import EvidenceChunkInput, EvidenceService
from src.qa_sets.schemas import (
    EvidenceCoverageRead,
    EvidenceRead,
    EvidenceWrite,
    GoldDocumentsWrite,
    ImportSummaryRead,
    QASetCreate,
    QASetDetail,
    QASetRead,
    QASetSnapshotCreate,
    QASetSnapshotCreated,
    QASetSnapshotRead,
    QuestionCreate,
    QuestionRead,
    QuestionUpdate,
)
from src.qa_sets.service import (
    AnswerRef,
    QASetService,
    QASetSnapshotService,
    QuestionDraft,
    QuestionService,
)
from src.qa_sets.utils import ExportFormat

router = APIRouter(prefix="/qa-sets", tags=["qa-sets"])
# Operations on one question, addressed by its id alone: a question belongs to exactly
# one set, so repeating the set in the path would only add a way to get it wrong.
questions_router = APIRouter(prefix="/questions", tags=["qa-sets"])


def _draft(payload: QuestionCreate) -> QuestionDraft:
    return QuestionDraft(
        text=payload.text,
        tags=payload.tags,
        answerable=payload.answerable,
        expected_answers=[
            AnswerRef(answer.text, answer.is_primary)
            for answer in payload.expected_answers
        ],
        gold_document_ids=payload.gold_document_ids,
    )


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
    chunking_configuration_id: Annotated[
        uuid.UUID | None,
        Query(
            description="Report each question's evidence status under this configuration."
        ),
    ] = None,
) -> QASetDetail:
    """Return a QA set with a page of its current questions and their gold documents."""
    service = QASetService(session)
    qa_set = await service.get(qa_set_id)
    questions, total = await service.list_questions(
        qa_set_id,
        limit=limit,
        offset=offset,
        chunking_configuration_id=chunking_configuration_id,
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


@router.post(
    "/{qa_set_id}/questions",
    response_model=QuestionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_question(
    qa_set_id: uuid.UUID, payload: QuestionCreate, session: SessionDep
) -> QuestionRead:
    """Write a question with its expected answers and, optionally, gold documents."""
    view = await QuestionService(session).create(qa_set_id, _draft(payload))
    return QuestionRead.model_validate(view)


@router.get("/{qa_set_id}/evidence-coverage", response_model=EvidenceCoverageRead)
async def get_evidence_coverage(
    qa_set_id: uuid.UUID,
    session: SessionDep,
    chunking_configuration_id: Annotated[uuid.UUID, Query()],
) -> EvidenceCoverageRead:
    """Count the questions of a set by the status of their evidence."""
    coverage = await QASetService(session).evidence_coverage(
        qa_set_id, chunking_configuration_id
    )
    return EvidenceCoverageRead.model_validate(coverage)


@router.get("/{qa_set_id}/export")
async def export_qa_set(
    qa_set_id: uuid.UUID,
    session: SessionDep,
    export_format: Annotated[ExportFormat, Query(alias="format")] = ExportFormat.JSONL,
    snapshot_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Response:
    """Download the questions in the format the import reads back."""
    exported = await QASetService(session).export(
        qa_set_id, export_format, snapshot_id=snapshot_id
    )
    return Response(
        content=exported.content,
        media_type=exported.media_type,
        headers={"Content-Disposition": f'attachment; filename="{exported.filename}"'},
    )


@questions_router.get("/{question_id}", response_model=QuestionRead)
async def get_question(
    question_id: uuid.UUID,
    session: SessionDep,
    chunking_configuration_id: Annotated[uuid.UUID | None, Query()] = None,
) -> QuestionRead:
    """Return a question, with its evidence status under a configuration if asked."""
    service = QuestionService(session)
    if chunking_configuration_id is not None:
        await service.qa_sets.require_configuration(chunking_configuration_id)
    view = await service.view(question_id, chunking_configuration_id)
    return QuestionRead.model_validate(view)


@questions_router.patch("/{question_id}", response_model=QuestionRead)
async def update_question(
    question_id: uuid.UUID, payload: QuestionUpdate, session: SessionDep
) -> QuestionRead:
    """Edit a question that no snapshot holds yet."""
    view = await QuestionService(session).update(
        question_id,
        text=payload.text,
        tags=payload.tags,
        answerable=payload.answerable,
        expected_answers=(
            None
            if payload.expected_answers is None
            else [AnswerRef(a.text, a.is_primary) for a in payload.expected_answers]
        ),
    )
    return QuestionRead.model_validate(view)


@questions_router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(question_id: uuid.UUID, session: SessionDep) -> Response:
    """Delete a question that no snapshot holds."""
    await QuestionService(session).delete(question_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@questions_router.post(
    "/{question_id}/replace",
    response_model=QuestionRead,
    status_code=status.HTTP_201_CREATED,
)
async def replace_question(
    question_id: uuid.UUID, payload: QuestionCreate, session: SessionDep
) -> QuestionRead:
    """Replace a question with a new one; snapshots keep the old one."""
    view = await QuestionService(session).replace(question_id, _draft(payload))
    return QuestionRead.model_validate(view)


@questions_router.put("/{question_id}/gold-documents", response_model=QuestionRead)
async def set_gold_documents(
    question_id: uuid.UUID, payload: GoldDocumentsWrite, session: SessionDep
) -> QuestionRead:
    """Set the gold documents of a question to exactly this list."""
    view = await QuestionService(session).set_gold_documents(
        question_id, payload.document_ids
    )
    return QuestionRead.model_validate(view)


@questions_router.get("/{question_id}/evidence", response_model=EvidenceRead)
async def get_evidence(
    question_id: uuid.UUID,
    session: SessionDep,
    chunking_configuration_id: Annotated[uuid.UUID, Query()],
) -> EvidenceRead:
    """Return the evidence chunks of a question under a chunking configuration."""
    view = await EvidenceService(session).get(question_id, chunking_configuration_id)
    return EvidenceRead.model_validate(view)


@questions_router.put("/{question_id}/evidence", response_model=EvidenceRead)
async def put_evidence(
    question_id: uuid.UUID, payload: EvidenceWrite, session: SessionDep
) -> EvidenceRead:
    """Save a draft, confirm the evidence chunks, or record that none was found."""
    view = await EvidenceService(session).put(
        question_id,
        payload.chunking_configuration_id,
        status=payload.status,
        chunks=[
            EvidenceChunkInput(c.chunk_id, c.relevance, c.graded_relevance)
            for c in payload.chunks
        ],
        annotator=payload.annotator,
    )
    return EvidenceRead.model_validate(view)
