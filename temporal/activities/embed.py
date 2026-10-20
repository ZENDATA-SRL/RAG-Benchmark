from __future__ import annotations

import asyncio
import dataclasses
import json
import uuid

from src.components.service import ComponentService
from src.indexes.repository import IndexBuildRepository
from src.infrastructure.storage import ObjectStorage, get_object_storage
from src.pipelines.exceptions import ProfileNotFoundError
from src.pipelines.models import EmbeddingProfile
from src.settings import get_settings
from temporalio import activity
from temporalio.exceptions import ApplicationError

from temporal.activities.reads import load_embedder_component
from temporal.components.embedders.shared import resolve_embedder
from temporal.config import activity_session


@dataclasses.dataclass
class EmbedBatchOutput:
    """Where one embedded batch was written and how many vectors it contains."""

    embedded_count: int
    output_uri: str


def embedding_batch_key(index_build_id: str, batch_offset: int) -> str:
    """Storage key of one embedded batch.

    Deterministic in the build and the offset, so the upsert finds a batch without its
    URI travelling through the workflow, and a retried batch overwrites itself.
    """
    return f"embeddings/{index_build_id}/{batch_offset}.json"


@activity.defn
async def embed_batch(
    index_build_id: str,
    embedding_profile_id: str,
    batch_offset: int,
    limit: int,
) -> EmbedBatchOutput:
    """Embed one page of a build's chunks and persist the vectors to object storage.

    The chunks are read here and not passed in: their text would make the activity input
    grow with the chunk size, past the payload limit (RT-O02). Each stored record carries
    the chunk text and its document next to the vector, so the upsert into the vector
    store reads only this file and never recomputes embeddings.

    Returns:
        How many chunks were embedded, zero when the page is past the end.

    Raises:
        ApplicationError: Non-retryable, if the vectors do not have the dimensions the
            profile declares: retrying would only produce the same wrong vectors.
    """
    profile_id = uuid.UUID(embedding_profile_id)
    async with activity_session() as session:
        rows = await IndexBuildRepository(session).list_chunks(
            uuid.UUID(index_build_id), limit=limit, offset=batch_offset
        )
        if not rows:
            return EmbedBatchOutput(embedded_count=0, output_uri="")
        profile = await session.get(EmbeddingProfile, profile_id)
        if profile is None:
            raise ProfileNotFoundError("embedding", profile_id)
        key, params = await load_embedder_component(session, profile_id)
        await ComponentService(session).validate_params(
            profile.component_version_id, params
        )
        dimensions = profile.dimensions
        records = [
            {
                "chunk_id": str(chunk.id),
                "document_id": str(document_id),
                "ordinal": chunk.ordinal,
                "text": chunk.text,
            }
            for chunk, document_id in rows
        ]

    texts = [record["text"] for record in records]
    vectors = await asyncio.to_thread(_embed_texts, key, params, texts)
    if dimensions is not None and any(len(vector) != dimensions for vector in vectors):
        raise ApplicationError(
            f"embedder returned {len(vectors[0])} dimensions, profile declares "
            f"{dimensions}",
            type="EmbeddingDimensionMismatch",
            non_retryable=True,
        )

    payload = {
        "index_build_id": index_build_id,
        "embedding_profile_id": embedding_profile_id,
        "batch_offset": batch_offset,
        "vectors": [
            {**record, "embedding": vector}
            for record, vector in zip(records, vectors, strict=True)
        ],
    }
    storage_uri = await asyncio.to_thread(
        _write_batch, index_build_id, batch_offset, payload
    )
    return EmbedBatchOutput(embedded_count=len(records), output_uri=storage_uri)


def _embed_texts(key: str, params: dict, texts: list[str]) -> list[list[float]]:
    embedder = resolve_embedder(key, params)
    return embedder.embed_documents(texts)


def _write_batch(index_build_id: str, batch_offset: int, payload: dict) -> str:
    data = json.dumps(payload).encode()
    return _storage().put_bytes(
        embedding_batch_key(index_build_id, batch_offset), data, "application/json"
    )


def _storage() -> ObjectStorage:
    return get_object_storage(get_settings())
