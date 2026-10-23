from __future__ import annotations

from fastapi import APIRouter

from src.dependencies import SessionDep
from src.retrieval.schemas import RetrieveRequest, RetrieveResponse
from src.retrieval.service import RetrievalService

router = APIRouter(tags=["retrieval"])


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(payload: RetrieveRequest, session: SessionDep) -> RetrieveResponse:
    """Search a ready index build: the retrieval tool exposed to answer systems."""
    result = await RetrievalService(session).search(
        index_build_id=payload.index_build_id,
        retrieval_profile_id=payload.retrieval_profile_id,
        query=payload.query,
        execution_id=payload.execution_id,
    )
    return RetrieveResponse.model_validate(result)
