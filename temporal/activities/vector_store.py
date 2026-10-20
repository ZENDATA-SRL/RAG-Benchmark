from __future__ import annotations

import asyncio
import json
import uuid

from src.indexes.models import IndexBuild
from src.infrastructure.storage import get_object_storage
from src.pipelines.exceptions import ProfileNotFoundError
from src.settings import get_settings
from temporalio import activity

from temporal.activities.embed import embedding_batch_key
from temporal.activities.reads import load_vector_store_component
from temporal.components import resolve_vector_store
from temporal.config import activity_session


async def _load_target(index_build_id: str) -> tuple[str, str, dict]:
    """Return the vector store key, the collection name and the index params of a build."""
    async with activity_session() as session:
        build = await session.get(IndexBuild, uuid.UUID(index_build_id))
        if build is None:
            raise ProfileNotFoundError("index build", index_build_id)
        key, index_params = await load_vector_store_component(
            session, build.vector_store_profile_id
        )
        return key, build.external_index_ref, index_params


@activity.defn
async def prepare_index_collection(index_build_id: str) -> None:
    """Create the build's collection with the vector store profile's configuration.

    The collection is named after `external_index_ref`; a re-run reuses it, since the
    upsert is keyed by chunk id and overwrites what a previous attempt wrote.
    """
    key, collection, index_params = await _load_target(index_build_id)
    store = resolve_vector_store(key)
    await asyncio.to_thread(store.ensure_collection, collection, index_params)


@activity.defn
async def upsert_embedding_batch(index_build_id: str, batch_offset: int) -> int:
    """Write one embedded batch from object storage into the vector store.

    Reads the file `embed_batch` wrote, so a failed upsert is retried without
    recomputing the embeddings. Returns how many vectors were written.
    """
    key, collection, _ = await _load_target(index_build_id)
    data = await asyncio.to_thread(
        get_object_storage(get_settings()).get_bytes,
        embedding_batch_key(index_build_id, batch_offset),
    )
    records = json.loads(data)["vectors"]
    store = resolve_vector_store(key)
    await asyncio.to_thread(
        store.upsert,
        collection,
        ids=[record["chunk_id"] for record in records],
        embeddings=[record["embedding"] for record in records],
        documents=[record["text"] for record in records],
        metadatas=[
            {
                "index_build_id": index_build_id,
                "document_id": record["document_id"],
                "ordinal": record["ordinal"],
            }
            for record in records
        ],
    )
    return len(records)
