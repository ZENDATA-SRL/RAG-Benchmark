from __future__ import annotations

import dataclasses
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from src.artifacts.service import ArtefactService
from src.components.builtin.chunkers import recursive
from src.components.builtin.parsers import pypdf
from src.components.registry_seed import seed_builtin_components
from src.components.repository import ComponentRepository, ComponentVersionRepository
from src.corpora.models import Corpus, CorpusDocument
from src.documents.models import Document
from src.infrastructure.database.enums import ComponentType, DocumentStatus
from src.infrastructure.storage.base import parse_key
from src.pipelines.models import ChunkingConfiguration, ParsingProfile
from src.pipelines.service import ChunkingConfigurationService, ProfileService


@dataclasses.dataclass
class Scenario:
    """A corpus and a chunking configuration in a known state of materialisation.

    Built through the real services, so what the API reads back is what a genuine run
    would have left behind: claimed artefacts, chunks with ordinals, coverage counts.
    """

    corpus: Corpus
    configuration: ChunkingConfiguration
    parsing_profile: ParsingProfile
    ready: list[Document]
    failed: list[Document]
    missing: list[Document]

    @property
    def documents(self) -> list[Document]:
        return [*self.ready, *self.failed, *self.missing]

    @property
    def corpus_id(self) -> str:
        return str(self.corpus.id)

    @property
    def configuration_id(self) -> str:
        return str(self.configuration.id)


async def make_document(session: AsyncSession, filename: str = "doc.pdf") -> Document:
    """A stored document, i.e. one that materialisation would accept."""
    document = Document(
        content_hash=uuid.uuid4().hex,
        filename=filename,
        mime_type="application/pdf",
        size_bytes=1234,
        storage_uri=f"s3://test-bucket/documents/{uuid.uuid4().hex}/{filename}",
        status=DocumentStatus.STORED,
    )
    session.add(document)
    await session.flush()
    return document


async def make_configuration(
    session: AsyncSession, *, chunk_size: int = 500
) -> tuple[ParsingProfile, ChunkingConfiguration]:
    """Seed the builtin registry, then compose a configuration on top of it."""
    await seed_builtin_components(session)
    components = ComponentRepository(session)
    versions = ComponentVersionRepository(session)
    parser_component = await components.get_by_type_and_key(
        ComponentType.PARSER, pypdf.KEY
    )
    chunker_component = await components.get_by_type_and_key(
        ComponentType.CHUNKER, recursive.KEY
    )
    assert parser_component is not None and chunker_component is not None
    parser = (await versions.list_versions(parser_component.id))[0]
    chunker = (await versions.list_versions(chunker_component.id))[0]

    profiles = ProfileService(session)
    parsing_profile, _ = await profiles.get_or_create_parsing_profile(
        name="parse", component_version_id=parser.id
    )
    chunking_profile, _ = await profiles.get_or_create_chunking_profile(
        name=f"chunk{chunk_size}",
        component_version_id=chunker.id,
        strategy=recursive.STRATEGY,
        chunk_size=chunk_size,
        overlap=50,
    )
    configuration, _ = await ChunkingConfigurationService(session).get_or_create(
        parsing_profile_id=parsing_profile.id,
        chunking_profile_id=chunking_profile.id,
    )
    return parsing_profile, configuration


async def materialise(
    session: AsyncSession,
    document: Document,
    parsing_profile: ParsingProfile,
    configuration: ChunkingConfiguration,
    *,
    chunk_count: int = 1,
    error: str | None = None,
) -> None:
    """Take one document through parse and chunk, ending either ready or failed."""
    artefacts = ArtefactService(session)
    parse = await artefacts.claim_parsing_result(
        document_id=document.id, parsing_profile_id=parsing_profile.id
    )
    await artefacts.complete_parsing_result(
        parse,
        output_uri=f"s3://test-bucket/{parse_key(parsing_profile.config_hash, document.content_hash)}",
        output_text="parsed text",
    )
    chunk_result = await artefacts.claim_chunk_result(
        document_id=document.id,
        chunking_configuration_id=configuration.id,
        parsing_result=parse,
    )
    if error is not None:
        await artefacts.fail_artefact(chunk_result, error=error)
        return
    await artefacts.complete_chunk_result(
        chunk_result,
        [
            {
                "text": f"chunk {ordinal} of {document.filename} at size "
                f"{configuration.config_hash[:6]}",
                "metadata": {"page": ordinal + 1},
            }
            for ordinal in range(chunk_count)
        ],
    )


async def build_scenario(
    session: AsyncSession,
    *,
    ready: int = 0,
    failed: int = 0,
    missing: int = 0,
    chunks_per_document: int = 1,
    chunk_size: int = 500,
) -> Scenario:
    """A corpus of `ready + failed + missing` documents, materialised accordingly."""
    parsing_profile, configuration = await make_configuration(
        session, chunk_size=chunk_size
    )
    corpus = Corpus(name=f"corpus {uuid.uuid4().hex[:8]}")
    session.add(corpus)
    await session.flush()

    groups: dict[str, list[Document]] = {"ready": [], "failed": [], "missing": []}
    for group, count in (("ready", ready), ("failed", failed), ("missing", missing)):
        for index in range(count):
            document = await make_document(session, filename=f"{group}-{index}.pdf")
            session.add(CorpusDocument(corpus_id=corpus.id, document_id=document.id))
            groups[group].append(document)
    await session.flush()

    for document in groups["ready"]:
        await materialise(
            session,
            document,
            parsing_profile,
            configuration,
            chunk_count=chunks_per_document,
        )
    for document in groups["failed"]:
        await materialise(
            session, document, parsing_profile, configuration, error="boom"
        )

    return Scenario(
        corpus=corpus,
        configuration=configuration,
        parsing_profile=parsing_profile,
        ready=groups["ready"],
        failed=groups["failed"],
        missing=groups["missing"],
    )
