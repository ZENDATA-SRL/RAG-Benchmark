from __future__ import annotations

import uuid

import pytest
from src.components.builtin.chunkers import recursive
from src.components.builtin.parsers import pypdf
from src.components.service import ComponentService
from src.documents.models import Document
from src.infrastructure.database.enums import ArtifactStatus, ComponentType, DocumentStatus
from src.pipelines.repository import ChunkRepository
from src.pipelines.service import (
    ArtefactService,
    ChunkingConfigurationService,
    MaterializationRunService,
    ProfileService,
)

pytestmark = pytest.mark.integration


async def _document(session) -> Document:
    document = Document(
        content_hash=uuid.uuid4().hex,
        filename="doc.pdf",
        mime_type="application/pdf",
        size_bytes=1234,
        storage_uri="s3://bucket/documents/x/doc.pdf",
        status=DocumentStatus.STORED,
    )
    session.add(document)
    await session.flush()
    return document


async def _configuration(session):
    """Build a parsing profile, chunking profile and their configuration."""
    components = ComponentService(session)
    profiles = ProfileService(session)

    parser_component = await components.register_component(
        ComponentType.PARSER, pypdf.KEY, "PyPDF"
    )
    parser_version = await components.register_version(
        component_id=parser_component.id, version="1", params_schema=pypdf.PARAMS_SCHEMA
    )
    chunker_component = await components.register_component(
        ComponentType.CHUNKER, recursive.KEY, "Recursive"
    )
    chunker_version = await components.register_version(
        component_id=chunker_component.id,
        version="1",
        params_schema=recursive.PARAMS_SCHEMA,
        capabilities=recursive.CAPABILITIES,
    )

    parsing_profile, _ = await profiles.get_or_create_parsing_profile(
        name="parse", component_version_id=parser_version.id
    )
    chunking_profile, _ = await profiles.get_or_create_chunking_profile(
        name="chunk",
        component_version_id=chunker_version.id,
        strategy=recursive.STRATEGY,
        chunk_size=500,
        overlap=50,
    )
    configuration, _ = await ChunkingConfigurationService(session).get_or_create(
        parsing_profile_id=parsing_profile.id,
        chunking_profile_id=chunking_profile.id,
    )
    return parsing_profile, configuration


async def _ready_chunk_result(session, document, parsing_profile, configuration):
    artefacts = ArtefactService(session)
    parse = await artefacts.claim_parsing_result(
        document_id=document.id, parsing_profile_id=parsing_profile.id
    )
    await artefacts.complete_parsing_result(parse, output_uri="s3://bucket/parses/x.json")
    chunk_result = await artefacts.claim_chunk_result(
        document_id=document.id,
        chunking_configuration_id=configuration.id,
        parsing_result=parse,
    )
    return artefacts, chunk_result


async def test_rematerialisation_clears_orphan_chunks(session) -> None:
    """A failed chunk result re-run must drop its orphans, or the unique (id, ordinal) fails."""
    document = await _document(session)
    parsing_profile, configuration = await _configuration(session)
    artefacts, chunk_result = await _ready_chunk_result(
        session, document, parsing_profile, configuration
    )

    # First attempt writes two chunks, then fails.
    await artefacts.complete_chunk_result(
        chunk_result, [{"text": "a"}, {"text": "b"}]
    )
    await artefacts.fail_artefact(chunk_result, error="boom")

    # Re-materialisation: clear orphans, then rewrite from ordinal 0 without a violation.
    removed = await ChunkRepository(session).delete_by_chunk_result(chunk_result.id)
    assert removed == 2
    await artefacts.complete_chunk_result(
        chunk_result, [{"text": "x"}, {"text": "y"}, {"text": "z"}]
    )

    assert chunk_result.status is ArtifactStatus.READY
    assert chunk_result.chunk_count == 3


async def test_materialisation_run_progress_is_monotonic_and_sums(session) -> None:
    _, configuration = await _configuration(session)
    runs = MaterializationRunService(session)
    workflow_id = f"materialize-{configuration.id}-digest"

    run = await runs.open_run(
        workflow_id=workflow_id,
        chunking_configuration_id=configuration.id,
        document_count=20,
    )
    assert run.status is ArtifactStatus.RUNNING
    assert run.progress["pending"] == 20

    await runs.update_progress(
        workflow_id=workflow_id, progress={"ready": 5, "failed": 1, "cached": 4}
    )
    mid = await runs.runs.get_by_workflow_id(workflow_id)
    assert mid is not None
    assert mid.progress["pending"] == 10

    final = await runs.complete_run(
        workflow_id=workflow_id, progress={"ready": 15, "failed": 1, "cached": 4}
    )
    assert final is not None
    total = final.progress["ready"] + final.progress["failed"] + final.progress["cached"]
    assert total + final.progress["pending"] == final.document_count
    assert final.status is ArtifactStatus.FAILED
    assert final.finished_at is not None


async def test_open_run_is_idempotent_on_workflow_id(session) -> None:
    _, configuration = await _configuration(session)
    runs = MaterializationRunService(session)
    workflow_id = f"materialize-{configuration.id}-digest"

    first = await runs.open_run(
        workflow_id=workflow_id,
        chunking_configuration_id=configuration.id,
        document_count=3,
    )
    second = await runs.open_run(
        workflow_id=workflow_id,
        chunking_configuration_id=configuration.id,
        document_count=3,
    )
    assert first.id == second.id
