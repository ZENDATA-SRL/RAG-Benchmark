from __future__ import annotations

import asyncio
import dataclasses
import json
import uuid

from src.components.service import ComponentService
from src.infrastructure.storage import ObjectStorage, get_object_storage
from src.pipelines.models import EmbeddingProfile
from src.settings import get_settings
from temporalio import activity

from temporal.activities.indexing import ChunkForEmbedding
from temporal.activities.reads import load_embedder_component
from temporal.components.embedders.shared import resolve_embedder
from temporal.config import activity_session


@dataclasses.dataclass
class EmbedBatchOutput:
    """Where one embedded batch was written and how many vectors it contains."""

    embedded_count: int
    output_uri: str


@activity.defn
async def embed_batch(
    index_build_id: str,
    embedding_profile_id: str,
    batch_offset: int,
    chunks: list[ChunkForEmbedding],
) -> EmbedBatchOutput:
    """Embed one batch of chunks and persist the vectors to object storage (RT-O02).

    Vectors are written under `embeddings/{index_build_id}/{batch_offset}.json` so a later
    activity can upsert them into the vector store without recomputing embeddings.
    """
    if not chunks:
        return EmbedBatchOutput(embedded_count=0, output_uri="")

    profile_id = uuid.UUID(embedding_profile_id)
    async with activity_session() as session:
        profile = await session.get(EmbeddingProfile, profile_id)
        if profile is None:
            from src.pipelines.exceptions import ProfileNotFoundError

            raise ProfileNotFoundError("embedding", profile_id)
        key, params = await load_embedder_component(session, profile_id)
        await ComponentService(session).validate_params(profile.component_version_id, params)

    texts = [chunk.text for chunk in chunks]
    vectors = await asyncio.to_thread(_embed_texts, key, params, texts)
    payload = {
        "index_build_id": index_build_id,
        "embedding_profile_id": embedding_profile_id,
        "batch_offset": batch_offset,
        "vectors": [
            {"chunk_id": chunk.chunk_id, "embedding": vector}
            for chunk, vector in zip(chunks, vectors, strict=True)
        ],
    }
    storage_uri = await asyncio.to_thread(
        _write_batch, index_build_id, batch_offset, payload
    )
    return EmbedBatchOutput(embedded_count=len(chunks), output_uri=storage_uri)


def _embed_texts(key: str, params: dict, texts: list[str]) -> list[list[float]]:
    embedder = resolve_embedder(key, params)
    return embedder.embed_documents(texts)


def _write_batch(index_build_id: str, batch_offset: int, payload: dict) -> str:
    key = f"embeddings/{index_build_id}/{batch_offset}.json"
    data = json.dumps(payload).encode()
    return _storage().put_bytes(key, data, "application/json")


def _storage() -> ObjectStorage:
    return get_object_storage(get_settings())
