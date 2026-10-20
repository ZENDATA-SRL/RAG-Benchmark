from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import uuid

from src.artifacts.service import ArtefactService
from src.components.service import ComponentService
from src.infrastructure.storage import ObjectStorage, get_object_storage, storage_key
from src.pipelines.models import ChunkingConfiguration, ChunkingProfile
from src.settings import get_settings
from temporalio import activity

from temporal.activities.reads import load_chunking_component
from temporal.components import resolve_chunker
from temporal.config import activity_session

logger = logging.getLogger(__name__)

# A single document rarely yields this many chunks; crossing it signals a chunk_size set far
# too small, not a failure — hence a warning, not an error.
_CHUNK_COUNT_WARNING = 10_000


@dataclasses.dataclass
class ChunkResultOutput:
    """What `chunk_document` returns: the artefact id and how many chunks it holds."""

    chunk_result_id: str
    chunk_count: int


@activity.defn
async def chunk_document(
    document_id: str, chunking_configuration_id: str, parsing_result_id: str
) -> ChunkResultOutput:
    """Chunk one document under one configuration, from a parse of the same document.

    Claims the chunk result (the parse/profile coherence check is inside the service), reads
    the parse from storage, resolves and validates the builtin chunker, runs it, and
    completes the artefact. If a previous attempt left a `failed` result behind, its orphan
    chunks are cleared first so the unique `(chunk_result_id, ordinal)` does not fail the
    retry.
    """
    doc_id = uuid.UUID(document_id)
    config_id = uuid.UUID(chunking_configuration_id)
    parse_id = uuid.UUID(parsing_result_id)

    async with activity_session() as session:
        artefacts = ArtefactService(session)
        parsing_result = await artefacts.parsing_results.get_by_id(parse_id)
        if parsing_result is None:
            from src.pipelines.exceptions import ProfileNotFoundError

            raise ProfileNotFoundError("parsing result", parse_id)

        chunk_result = await artefacts.claim_chunk_result(
            document_id=doc_id,
            chunking_configuration_id=config_id,
            parsing_result=parsing_result,
        )
        if chunk_result.status.value == "ready":
            return ChunkResultOutput(str(chunk_result.id), chunk_result.chunk_count)

        # Re-materialisation of a failed attempt: drop the orphan chunks before rewriting.
        if chunk_result.status.value == "failed":
            await artefacts.chunks.delete_by_chunk_result(chunk_result.id)

        configuration = await session.get(ChunkingConfiguration, config_id)
        assert configuration is not None  # claim_chunk_result validated it exists
        key, params = await load_chunking_component(
            session, configuration.chunking_profile_id
        )
        profile = await session.get(ChunkingProfile, configuration.chunking_profile_id)
        assert profile is not None
        await ComponentService(session).validate_params(
            profile.component_version_id, params
        )

        parse_output = await asyncio.to_thread(_read_parse, parsing_result.output_uri)
        chunks = await asyncio.to_thread(_run_chunker, key, parse_output, params)

        if len(chunks) > _CHUNK_COUNT_WARNING:
            logger.warning(
                "document %s produced %d chunks under configuration %s; check chunk_size",
                document_id,
                len(chunks),
                chunking_configuration_id,
            )

        completed = await artefacts.complete_chunk_result(chunk_result, chunks)
        return ChunkResultOutput(str(completed.id), completed.chunk_count)


def _run_chunker(key: str, parse_output: dict, params: dict) -> list[dict]:
    chunker = resolve_chunker(key)
    return list(chunker.chunk(parse_output, params))


def _read_parse(output_uri: str | None) -> dict:
    assert output_uri is not None  # a ready parse always has an output (DB CHECK)
    raw = _storage().get_bytes(storage_key(output_uri))
    return json.loads(raw)


def _storage() -> ObjectStorage:
    return get_object_storage(get_settings())
