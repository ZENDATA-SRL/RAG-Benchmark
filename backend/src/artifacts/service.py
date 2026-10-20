from __future__ import annotations

import asyncio
import dataclasses
import json
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.artifacts.exceptions import (
    ChunkNotFoundError,
    ChunkResultNotFoundError,
    ParsingProfileMismatchError,
    ParsingResultNotFoundError,
    ParsingResultNotReadyError,
)
from src.artifacts.models import Chunk, ChunkResult, ParsingResult
from src.artifacts.repository import (
    ChunkRepository,
    ChunkResultRepository,
    ParsingResultRepository,
)
from src.core.get_or_create import get_or_create
from src.core.hashing import cache_key
from src.corpora.repository import CorpusDocumentRepository
from src.corpora.service import CorpusService
from src.documents.exceptions import DocumentNotFoundError
from src.documents.repository import DocumentRepository
from src.infrastructure.database.enums import ArtifactStatus
from src.infrastructure.storage import ObjectStorage, storage_key
from src.pipelines.exceptions import (
    ChunkingConfigurationNotFoundError,
    ProfileNotFoundError,
)
from src.pipelines.models import ParsingProfile
from src.pipelines.repository import ChunkingConfigurationRepository, ProfileRepository
from src.pipelines.service import ChunkingConfigurationService


class ArtefactService:
    """Claiming and completion of the per-document artefacts.

    Artefacts are claimed as `pending` on their cache key, which turns the unique index
    into the mutual exclusion between concurrent workers: the worker that inserts the row
    owns the work, the others reuse it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.parsing_results = ParsingResultRepository(session)
        self.chunk_results = ChunkResultRepository(session)
        self.chunks = ChunkRepository(session)
        self.documents = DocumentRepository(session)
        self.configurations = ChunkingConfigurationRepository(session)
        self.parsing_profiles = ProfileRepository(session, ParsingProfile)

    async def claim_parsing_result(
        self, *, document_id: uuid.UUID, parsing_profile_id: uuid.UUID
    ) -> ParsingResult:
        """Return the parse of a (document, parsing profile) pair, claiming it if absent.

        Returns:
            The cached parse — `ready` results are reused as they are — or a
            freshly claimed `pending` row for the caller to fill in.

        Raises:
            ProfileNotFoundError: If the document or the parsing profile does not exist.
        """
        document = await self.documents.get_by_id(document_id)
        if document is None:
            raise ProfileNotFoundError("document", document_id)
        profile = await self.parsing_profiles.get_by_id(parsing_profile_id)
        if profile is None:
            raise ProfileNotFoundError("parsing", parsing_profile_id)

        key = cache_key(document.content_hash, profile.config_hash)

        async def create() -> ParsingResult:
            result = self.parsing_results.add(
                ParsingResult(
                    document_id=document_id,
                    parsing_profile_id=parsing_profile_id,
                    cache_key=key,
                )
            )
            await self.session.flush()
            return result

        return await get_or_create(
            self.session,
            lookup=lambda: self.parsing_results.get_by_cache_key(key),
            create=create,
        )

    async def complete_parsing_result(
        self, parsing_result: ParsingResult, *, output_uri: str, output_text: str
    ) -> ParsingResult:
        """Mark a parse as `ready` with the storage reference of its output (RT-O02)."""
        parsing_result.output_uri = output_uri
        parsing_result.output_text = output_text
        parsing_result.status = ArtifactStatus.READY
        parsing_result.error = None
        await self.session.flush()
        return parsing_result

    async def claim_chunk_result(
        self,
        *,
        document_id: uuid.UUID,
        chunking_configuration_id: uuid.UUID,
        parsing_result: ParsingResult,
    ) -> ChunkResult:
        """Return the chunk result of a (document, configuration) pair, claiming it if absent.

        Args:
            document_id: Document being chunked.
            chunking_configuration_id: Configuration the chunks belong to.
            parsing_result: The parse used as input; must be `ready` and produced by the
                parsing profile the configuration declares.

        Raises:
            ProfileNotFoundError: If the document or the configuration does not exist.
            ParsingResultNotReadyError: If the input parse has not succeeded.
            ParsingProfileMismatchError: If the parse comes from another parsing profile.
        """
        document = await self.documents.get_by_id(document_id)
        if document is None:
            raise ProfileNotFoundError("document", document_id)
        configuration = await self.configurations.get_by_id(chunking_configuration_id)
        if configuration is None:
            raise ProfileNotFoundError(
                "chunking configuration", chunking_configuration_id
            )

        if parsing_result.status is not ArtifactStatus.READY:
            raise ParsingResultNotReadyError(parsing_result.id, parsing_result.status)
        if parsing_result.parsing_profile_id != configuration.parsing_profile_id:
            raise ParsingProfileMismatchError(
                configuration.parsing_profile_id, parsing_result.parsing_profile_id
            )
        if parsing_result.document_id != document_id:
            raise ParsingProfileMismatchError(document_id, parsing_result.document_id)

        key = cache_key(document.content_hash, configuration.config_hash)

        async def create() -> ChunkResult:
            result = self.chunk_results.add(
                ChunkResult(
                    document_id=document_id,
                    chunking_configuration_id=chunking_configuration_id,
                    parsing_result_id=parsing_result.id,
                    parsing_profile_id=configuration.parsing_profile_id,
                    cache_key=key,
                )
            )
            await self.session.flush()
            return result

        return await get_or_create(
            self.session,
            lookup=lambda: self.chunk_results.get_by_cache_key(key),
            create=create,
        )

    async def complete_chunk_result(
        self, chunk_result: ChunkResult, chunks: Sequence[dict[str, Any]]
    ) -> ChunkResult:
        """Persist the chunks of a document and mark the result `ready`.

        Ordinals are assigned by position, so the identity of a chunk stays
        (document, configuration, position) and confirmed gold survives re-runs.

        Args:
            chunk_result: The claimed row to complete.
            chunks: Chunk payloads in document order, with `text` and optionally
                `modality`, `metadata` and `text_normalized`.
        """
        self.chunks.add_all(
            Chunk(
                chunk_result_id=chunk_result.id,
                ordinal=ordinal,
                text=payload["text"],
                modality=payload.get("modality", "text"),
                chunk_metadata=payload.get("metadata", {}),
                text_normalized=payload.get("text_normalized"),
            )
            for ordinal, payload in enumerate(chunks)
        )
        chunk_result.chunk_count = len(chunks)
        chunk_result.status = ArtifactStatus.READY
        chunk_result.error = None
        await self.session.flush()
        return chunk_result

    async def fail_artefact(
        self, artefact: ParsingResult | ChunkResult, *, error: str
    ) -> ParsingResult | ChunkResult:
        """Mark an artefact as failed without interrupting the rest of the run (RT-O06)."""
        artefact.status = ArtifactStatus.FAILED
        artefact.error = error
        await self.session.flush()
        return artefact

    async def documents_needing_chunking(
        self, document_ids: Sequence[uuid.UUID], chunking_configuration_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """Documents without a `ready` chunk result for a configuration.

        This is what makes growing a corpus cheap: only the new documents are
        chunked, the ones already materialised are reused as they are.
        """
        existing = await self.chunk_results.list_by_documents(
            document_ids, chunking_configuration_id
        )
        ready = {
            result.document_id
            for result in existing
            if result.status is ArtifactStatus.READY
        }
        return [document_id for document_id in document_ids if document_id not in ready]


@dataclasses.dataclass(frozen=True)
class ConfigurationCoverage:
    """How far a configuration has been materialised over a set of documents.

    Answers the question the user actually asks — *is this configuration ready on this
    corpus?* — with numbers that always sum to `total`, so a missing document is visible as
    a number and not as an absence.
    """

    total: int
    ready: int
    failed: int
    missing: int


class CoverageService:
    """How far a chunking configuration has been materialised over a corpus."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.chunk_results = ChunkResultRepository(session)
        self.corpus_documents = CorpusDocumentRepository(session)

    async def coverage(
        self, configuration_id: uuid.UUID, corpus_id: uuid.UUID
    ) -> ConfigurationCoverage:
        """Count how many documents of a corpus this configuration has materialised.

        `missing` is derived rather than queried, which is what guarantees the invariant the
        caller relies on: the three numbers always add up to the corpus size, so a document
        with no chunk result at all is counted and not silently dropped.

        Raises:
            ChunkingConfigurationNotFoundError: If the configuration does not exist.
            CorpusNotFoundError: If the corpus does not exist.
        """
        await ChunkingConfigurationService(self.session).get(configuration_id)
        await CorpusService(self.session).get(corpus_id)

        document_ids = await self.corpus_documents.list_document_ids(corpus_id)
        by_status = await self.chunk_results.count_by_status(
            document_ids, configuration_id
        )
        ready = by_status.get(ArtifactStatus.READY, 0)
        failed = by_status.get(ArtifactStatus.FAILED, 0)
        total = len(document_ids)
        return ConfigurationCoverage(
            total=total,
            ready=ready,
            failed=failed,
            missing=max(total - ready - failed, 0),
        )


@dataclasses.dataclass(frozen=True)
class ParsePage:
    """One page of a parse output, as stored in the JSON on object storage."""

    page: int
    text: str


class InspectionService:
    """Reading back what parsing and chunking produced, per document (RF-P08).

    The point of the platform is to make the two stages *visible*: "the chunking looks
    strange" almost always means "the parse looks strange", and without a way to look at each
    stage separately the user cannot tell which one to change.
    """

    def __init__(self, session: AsyncSession, storage: ObjectStorage) -> None:
        self.session = session
        self.storage = storage
        self.documents = DocumentRepository(session)
        self.chunks = ChunkRepository(session)
        self.chunk_results = ChunkResultRepository(session)
        self.parsing_results = ParsingResultRepository(session)
        self.configurations = ChunkingConfigurationRepository(session)

    async def get_chunk_result(
        self, *, document_id: uuid.UUID, chunking_configuration_id: uuid.UUID
    ) -> ChunkResult:
        """Return the chunk result of a (document, configuration) pair.

        Raises:
            DocumentNotFoundError: If the document does not exist.
            ChunkingConfigurationNotFoundError: If the configuration does not exist.
            ChunkResultNotFoundError: If the pair was never materialised.
        """
        await self._assert_document(document_id)
        if await self.configurations.get_by_id(chunking_configuration_id) is None:
            raise ChunkingConfigurationNotFoundError(chunking_configuration_id)
        result = await self.chunk_results.get_by_document_and_configuration(
            document_id, chunking_configuration_id
        )
        if result is None:
            raise ChunkResultNotFoundError(document_id, chunking_configuration_id)
        return result

    async def list_chunks(
        self,
        *,
        document_id: uuid.UUID,
        chunking_configuration_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[Sequence[Chunk], int, ChunkResult]:
        """One page of the chunks of a document under a configuration, in `ordinal` order.

        Returns:
            The window of chunks, how many there are in total, and the chunk result they
            belong to, so the caller can report its status alongside them.
        """
        result = await self.get_chunk_result(
            document_id=document_id, chunking_configuration_id=chunking_configuration_id
        )
        chunks = await self.chunks.list_by_chunk_result(
            result.id, limit=limit, offset=offset
        )
        total = await self.chunks.count_by_chunk_result(result.id)
        return chunks, total, result

    async def get_chunk(self, chunk_id: uuid.UUID) -> Chunk:
        """Return a single chunk by id, for the side panel of the UI.

        Raises:
            ChunkNotFoundError: If it does not exist.
        """
        chunk = await self.chunks.get_by_id(chunk_id)
        if chunk is None:
            raise ChunkNotFoundError(chunk_id)
        return chunk

    async def parse_pages(
        self,
        *,
        document_id: uuid.UUID,
        parsing_profile_id: uuid.UUID,
        limit: int = 10,
        offset: int = 0,
    ) -> tuple[list[ParsePage], int, ParsingResult]:
        """One window of the per-page text of a parse, read from object storage.

        Paginated by page because a parse of a few hundred pages is megabytes of text: the
        whole document is never sent to render one page of it.

        Returns:
            The requested pages, the page count of the whole parse, and the parse row.

        Raises:
            DocumentNotFoundError: If the document does not exist.
            ParsingResultNotFoundError: If the pair was never parsed.
            ParsingResultNotReadyError: If the parse has not succeeded, so there is no output.
        """
        await self._assert_document(document_id)
        result = await self.parsing_results.get_by_document_and_profile(
            document_id, parsing_profile_id
        )
        if result is None:
            raise ParsingResultNotFoundError(document_id, parsing_profile_id)
        if result.status is not ArtifactStatus.READY or result.output_uri is None:
            raise ParsingResultNotReadyError(result.id, result.status)

        payload = await asyncio.to_thread(
            self.storage.get_bytes, storage_key(result.output_uri)
        )
        pages = json.loads(payload).get("pages", [])
        window = [
            ParsePage(page=int(page.get("page", index + 1)), text=page.get("text", ""))
            for index, page in enumerate(pages[offset : offset + limit], start=offset)
        ]
        return window, len(pages), result

    async def _assert_document(self, document_id: uuid.UUID) -> None:
        if await self.documents.get_by_id(document_id) is None:
            raise DocumentNotFoundError(document_id)
