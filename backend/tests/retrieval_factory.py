from __future__ import annotations

import uuid
from collections.abc import Sequence

from langchain_core.embeddings import DeterministicFakeEmbedding
from sqlalchemy import select
from src.artifacts.models import Chunk, ChunkResult
from src.components.builtin.embedder import openai_embedder
from src.components.builtin.vector_stores import chroma
from src.components.repository import ComponentRepository, ComponentVersionRepository
from src.corpora.service import CorpusSnapshotService
from src.documents.models import Document
from src.indexes.models import IndexBuild
from src.indexes.service import IndexBuildService
from src.infrastructure.database.enums import ArtifactStatus, ComponentType
from src.pipelines.service import ProfileService
from tests.pipeline_factory import Scenario

from temporal.components.vector_stores.chroma import ChromaVectorStore

DIMENSIONS = 16


async def version_id(session, component_type: ComponentType, key: str) -> uuid.UUID:
    component = await ComponentRepository(session).get_by_type_and_key(
        component_type, key
    )
    assert component is not None
    return (await ComponentVersionRepository(session).list_versions(component.id))[0].id


async def indexed_build(
    session,
    scenario: Scenario,
    chroma_client,
    *,
    status=ArtifactStatus.READY,
    documents: Sequence[Document] | None = None,
) -> IndexBuild:
    """An index build over some documents (the ready ones by default), chunks in Chroma."""
    profiles = ProfileService(session)
    embedding, _ = await profiles.get_or_create_embedding_profile(
        name="fake",
        component_version_id=await version_id(
            session, ComponentType.EMBEDDER, openai_embedder.KEY
        ),
    )
    store_profile, _ = await profiles.get_or_create_vector_store_profile(
        name="chroma",
        component_version_id=await version_id(
            session, ComponentType.VECTOR_STORE, chroma.KEY
        ),
        index_params={"space": "cosine"},
    )
    chosen = list(documents if documents is not None else scenario.ready)
    snapshot = await CorpusSnapshotService(session).get_or_create(
        scenario.corpus.id, [document.id for document in chosen], label="v1"
    )
    build = await IndexBuildService(session).get_or_create(
        corpus_snapshot_id=snapshot.id,
        chunking_configuration_id=scenario.configuration.id,
        embedding_profile_id=embedding.id,
        vector_store_profile_id=store_profile.id,
    )
    rows = (
        await session.execute(
            select(Chunk, ChunkResult.document_id)
            .join(ChunkResult, ChunkResult.id == Chunk.chunk_result_id)
            .where(ChunkResult.document_id.in_([document.id for document in chosen]))
        )
    ).all()
    writer = ChromaVectorStore(chroma_client)
    writer.ensure_collection(build.external_index_ref, {"space": "cosine"})
    fake = DeterministicFakeEmbedding(size=DIMENSIONS)
    writer.upsert(
        build.external_index_ref,
        ids=[str(chunk.id) for chunk, _ in rows],
        embeddings=fake.embed_documents([chunk.text for chunk, _ in rows]),
        documents=[chunk.text for chunk, _ in rows],
        metadatas=[
            {"document_id": str(document_id), "ordinal": chunk.ordinal}
            for chunk, document_id in rows
        ],
        index_params={},
    )
    build.status = status
    await session.flush()
    return build
