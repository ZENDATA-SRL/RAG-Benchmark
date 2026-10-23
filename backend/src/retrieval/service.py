from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.components.builtin.contracts import VectorHit
from src.indexes.models import IndexBuild
from src.indexes.service import IndexBuildService
from src.infrastructure.database.enums import ArtifactStatus
from src.pipelines.exceptions import ProfileNotFoundError
from src.pipelines.models import RetrievalProfile
from src.pipelines.service import ProfileService
from src.retrieval.embedders import resolve_embedder
from src.retrieval.exceptions import IndexBuildNotReadyError, RetrievalBackendError
from src.retrieval.readers import resolve_reader
from src.retrieval.repository import RetrievalRepository

logger = logging.getLogger(__name__)

# Every hit comes out of the only stage that exists today. The field is there so that
# dense, sparse, fused and reranked hits can later be told apart without changing shape.
FINAL_STAGE = "final"


@dataclasses.dataclass(frozen=True)
class RetrievedHit:
    """One chunk returned by a query, enriched from the database."""

    rank: int
    score: float
    stage: str
    chunk_id: uuid.UUID | None
    document_id: uuid.UUID | None
    filename: str | None
    ordinal: int | None
    page: int | None
    text: str | None


@dataclasses.dataclass(frozen=True)
class RetrievalTimings:
    """Where the time of a query went, in milliseconds."""

    embed_ms: float
    search_ms: float
    enrich_ms: float
    total_ms: float


@dataclasses.dataclass(frozen=True)
class RetrievalResult:
    """The hits of one query, with what a caller needs to open them."""

    index_build_id: uuid.UUID
    retrieval_profile_id: uuid.UUID
    corpus_id: uuid.UUID | None
    chunking_configuration_id: uuid.UUID
    hits: list[RetrievedHit]
    timings: RetrievalTimings


class RetrievalService:
    """Dense search over a ready index build, the engine behind the retrieval tool."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = RetrievalRepository(session)
        self.profiles = ProfileService(session)

    async def search(
        self,
        *,
        index_build_id: uuid.UUID,
        retrieval_profile_id: uuid.UUID,
        query: str,
        execution_id: uuid.UUID | None = None,
    ) -> RetrievalResult:
        """Return the chunks of an index build closest to a query.

        Dense search, the only strategy a profile can have today, compares the query vector
        with the chunk vectors: the query is therefore embedded, with the embedding profile
        of the build and never one chosen by the caller, since vectors from different
        models are not comparable. Metadata filters are resolved to the matching documents
        of the build's snapshot before the vector store is asked. Scores are normalised so
        that higher is better on every store.

        Args:
            index_build_id: Index to search; it must be `ready`.
            retrieval_profile_id: Top-k, score threshold and metadata filters to apply.
            query: Text of the query.
            execution_id: Experiment execution the call belongs to, when an answer system
                makes it. Without one the call is a manual test query and is only logged.

        Returns:
            Hits ranked from 1, best first, and the time spent in each step.

        Raises:
            IndexBuildNotFoundError: If the build does not exist.
            IndexBuildNotReadyError: If the build is not `ready`.
            ProfileNotFoundError: If the retrieval or embedding profile does not exist.
            RetrievalBackendError: If the embedder or the vector store fails.
        """
        started = time.perf_counter()
        build = await IndexBuildService(self.session).get(index_build_id)
        if build.status != ArtifactStatus.READY:
            raise IndexBuildNotReadyError(build.id, build.status.value)
        profile = await self.profiles.get_retrieval_profile(retrieval_profile_id)
        embedding = await self.profiles.get_embedding_profile(
            build.embedding_profile_id
        )
        embedder_key = await self._component_key(
            embedding.component_version_id, "embedder"
        )
        store_key = await self._component_key(
            (
                await self.profiles.get_vector_store_profile(
                    build.vector_store_profile_id
                )
            ).component_version_id,
            "vector store",
        )
        document_ids = await self._document_filter(build, profile)

        embed_started = time.perf_counter()
        vector = await _call(
            "embedding", _embed_query, embedder_key, dict(embedding.params), query
        )
        search_started = time.perf_counter()
        raw_hits: list[VectorHit] = await _call(
            "vector store",
            _search,
            store_key,
            build.external_index_ref,
            vector,
            profile.top_k,
            document_ids,
        )
        enrich_started = time.perf_counter()
        if profile.score_threshold is not None:
            raw_hits = [hit for hit in raw_hits if hit.score >= profile.score_threshold]
        hits = await self._enrich(raw_hits)
        finished = time.perf_counter()

        timings = RetrievalTimings(
            embed_ms=_ms(embed_started, search_started),
            search_ms=_ms(search_started, enrich_started),
            enrich_ms=_ms(enrich_started, finished),
            total_ms=_ms(started, finished),
        )
        logger.info(
            "retrieval index_build=%s profile=%s execution=%s hits=%d total_ms=%.1f",
            build.id,
            profile.id,
            execution_id or "-",
            len(hits),
            timings.total_ms,
        )
        return RetrievalResult(
            index_build_id=build.id,
            retrieval_profile_id=profile.id,
            corpus_id=await self.repository.snapshot_corpus_id(
                build.corpus_snapshot_id
            ),
            chunking_configuration_id=build.chunking_configuration_id,
            hits=hits,
            timings=timings,
        )

    async def _component_key(self, component_version_id: uuid.UUID, kind: str) -> str:
        key = await self.repository.component_key(component_version_id)
        if key is None:
            raise ProfileNotFoundError(
                f"{kind} component version", component_version_id
            )
        return key

    async def _document_filter(
        self, build: IndexBuild, profile: RetrievalProfile
    ) -> list[str] | None:
        """Document ids the search is restricted to, or `None` for the whole snapshot."""
        if not profile.metadata_filters:
            return None
        matching = await self.repository.snapshot_documents_matching(
            build.corpus_snapshot_id, profile.metadata_filters
        )
        return [str(document_id) for document_id in matching]

    async def _enrich(self, raw_hits: list[VectorHit]) -> list[RetrievedHit]:
        """Attach chunk, document and page from the database to each vector hit.

        A vector whose chunk no longer exists is still returned, with a null `chunk_id`
        and the text the vector store kept, rather than failing the whole query.
        """
        chunk_ids = [_as_uuid(hit.id) for hit in raw_hits]
        found = await self.repository.chunks_by_id(
            [chunk_id for chunk_id in chunk_ids if chunk_id is not None]
        )
        hits = []
        for rank, (raw, chunk_id) in enumerate(
            zip(raw_hits, chunk_ids, strict=True), start=1
        ):
            row = found.get(chunk_id) if chunk_id is not None else None
            if row is None:
                hits.append(
                    RetrievedHit(
                        rank=rank,
                        score=raw.score,
                        stage=FINAL_STAGE,
                        chunk_id=None,
                        document_id=_as_uuid(raw.document_id),
                        filename=None,
                        ordinal=None,
                        page=None,
                        text=raw.text,
                    )
                )
                continue
            chunk, document_id, filename = row
            page = chunk.chunk_metadata.get("page")
            hits.append(
                RetrievedHit(
                    rank=rank,
                    score=raw.score,
                    stage=FINAL_STAGE,
                    chunk_id=chunk.id,
                    document_id=document_id,
                    filename=filename,
                    ordinal=chunk.ordinal,
                    page=page if isinstance(page, int) else None,
                    text=chunk.text,
                )
            )
        return hits


def _embed_query(key: str, params: dict, query: str) -> list[float]:
    return resolve_embedder(key, params).embed_query(query)


def _search(
    key: str,
    collection: str,
    vector: list[float],
    top_k: int,
    document_ids: list[str] | None,
) -> list[VectorHit]:
    return resolve_reader(key).query(
        collection, vector, top_k=top_k, document_ids=document_ids
    )


async def _call(stage: str, function, *args):
    """Run a blocking client call off the event loop, reporting its failure by stage."""
    try:
        return await asyncio.to_thread(function, *args)
    except Exception as error:
        logger.exception("retrieval %s failed", stage)
        raise RetrievalBackendError(
            stage, str(error) or type(error).__name__
        ) from error


def _as_uuid(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _ms(start: float, end: float) -> float:
    return round((end - start) * 1000, 2)
