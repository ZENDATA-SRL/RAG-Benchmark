from __future__ import annotations

import asyncio
import dataclasses
import io
import json
import uuid

from src.components.service import ComponentService
from src.infrastructure.storage import ObjectStorage, get_object_storage
from src.infrastructure.storage.base import parse_key
from src.pipelines.models import ParsingProfile
from src.pipelines.service import ArtefactService
from src.settings import get_settings
from temporalio import activity

from temporal.activities.reads import load_parsing_component
from temporal.components import resolve_parser
from temporal.components.parsers.exceptions import PermanentParsingError
from temporal.config import activity_session

_PROGRESS_HEARTBEAT_EVERY = 10


@dataclasses.dataclass
class ParseResult:
    """What `parse_document` returns to the workflow: the artefact id and its final status."""

    parsing_result_id: str
    status: str


@activity.defn
async def parse_document(document_id: str, parsing_profile_id: str) -> ParseResult:
    """Parse one document under one parsing profile, writing the output to storage (RF-P07).

    Steps: claim the parse (returning immediately if a ready one is cached), download the
    document, resolve and validate the builtin parser, parse, write the JSON to
    `parses/{config_hash}/{content_hash}.json`, and complete the artefact.

    A `PermanentParsingError` (corrupt, encrypted, or no extractable text) marks the
    artefact `failed` and returns normally, so the parent workflow can carry on with the
    other documents. It is re-raised as a non-retryable error only after being recorded, so
    Temporal does not retry a failure that will never change.
    """
    doc_id = uuid.UUID(document_id)
    profile_id = uuid.UUID(parsing_profile_id)

    async with activity_session() as session:
        artefacts = ArtefactService(session)
        parsing_result = await artefacts.claim_parsing_result(
            document_id=doc_id, parsing_profile_id=profile_id
        )
        if parsing_result.status.value == "ready":
            return ParseResult(str(parsing_result.id), "ready")

        profile = await session.get(ParsingProfile, profile_id)
        assert profile is not None  # claim_parsing_result already validated it exists
        content_hash, storage_uri = await _document_location(session, doc_id)
        key, params = await load_parsing_component(session, profile_id)

        try:
            await ComponentService(session).validate_params(
                profile.component_version_id, params
            )
            output = await asyncio.to_thread(
                _run_parser, key, storage_uri, document_id, params
            )
        except PermanentParsingError as error:
            await artefacts.fail_artefact(
                parsing_result, error=f"{error.reason}: {error}"
            )
            return ParseResult(str(parsing_result.id), "failed")

        output_key = parse_key(profile.config_hash, content_hash)
        await asyncio.to_thread(_write_parse, output_key, output)
        completed = await artefacts.complete_parsing_result(
            parsing_result, output_uri=_storage().build_uri(output_key)
        )
        return ParseResult(str(completed.id), "ready")


def _run_parser(key: str, storage_uri: str, filename: str, params: dict) -> dict:
    """Download the document and run the parser in a worker thread.

    Heartbeats per page (RT-O04): on a 500-page PDF this is what tells a timeout apart from
    slow progress and lets a retry resume rather than restart.
    """
    parser = resolve_parser(key)
    storage = _storage()
    with storage.get_stream(_uri_to_key(storage_uri)) as body:
        data = body.read()
    output = parser.parse(io.BytesIO(data), filename)
    for index, _ in enumerate(output["pages"], start=1):
        if index % _PROGRESS_HEARTBEAT_EVERY == 0:
            activity.heartbeat(index)
    activity.heartbeat(len(output["pages"]))
    return output


def _write_parse(key: str, output: dict) -> None:
    payload = json.dumps(output, ensure_ascii=False).encode("utf-8")
    _storage().put_bytes(key, payload, "application/json")


async def _document_location(session, document_id: uuid.UUID) -> tuple[str, str]:
    from src.pipelines.exceptions import ProfileNotFoundError

    artefacts = ArtefactService(session)
    document = await artefacts.documents.get_by_id(document_id)
    if document is None:
        raise ProfileNotFoundError("document", document_id)
    return document.content_hash, document.storage_uri


def _storage() -> ObjectStorage:
    return get_object_storage(get_settings())


def _uri_to_key(storage_uri: str) -> str:
    """Turn an `s3://bucket/key` URI back into the key the storage client expects."""
    without_scheme = storage_uri.removeprefix("s3://")
    _, _, key = without_scheme.partition("/")
    return key
