from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.components.models import ComponentVersion
from src.core.get_or_create import get_or_create
from src.core.hashing import (
    cache_key,
    chain_fingerprint,
    combined_config_hash,
    config_hash,
    hash_json,
)
from src.corpora.repository import CorpusSnapshotRepository
from src.documents.repository import DocumentRepository
from src.infrastructure.database.enums import ArtifactStatus
from src.pipelines.exceptions import (
    ParsingProfileMismatchError,
    ParsingResultNotReadyError,
    ProfileNotFoundError,
    UnsupportedChunkerScopeError,
)
from src.pipelines.models import (
    Chunk,
    ChunkingConfiguration,
    ChunkingProfile,
    ChunkResult,
    EmbeddingProfile,
    IndexBuild,
    MaterializationRun,
    ParsingProfile,
    ParsingResult,
    RetrievalProfile,
    VectorStoreProfile,
)
from src.pipelines.repository import (
    ChunkingConfigurationRepository,
    ChunkRepository,
    ChunkResultRepository,
    IndexBuildRepository,
    MaterializationRunRepository,
    ParsingResultRepository,
    ProfileRepository,
)

SUPPORTED_CHUNKER_SCOPE = "document"


class ProfileService:
    """Creation of pipeline profiles, deduplicated by `config_hash`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_parsing_profile(
        self, *, name: str, component_version_id: uuid.UUID, params: dict[str, Any] | None = None
    ) -> ParsingProfile:
        """Return the parsing profile for a (component version, params) pair."""
        return await self._get_or_create(
            ParsingProfile,
            component_version_id=component_version_id,
            name=name,
            columns={"params": params or {}},
        )

    async def get_or_create_chunking_profile(
        self,
        *,
        name: str,
        component_version_id: uuid.UUID,
        strategy: str,
        chunk_size: int | None = None,
        overlap: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> ChunkingProfile:
        """Return the chunking profile for a chunker configuration.

        Raises:
            UnsupportedChunkerScopeError: If the component version declares a scope other
                than `document`.
            ProfileNotFoundError: If the component version does not exist.
        """
        await self._assert_document_scope(component_version_id)
        return await self._get_or_create(
            ChunkingProfile,
            component_version_id=component_version_id,
            name=name,
            columns={
                "strategy": strategy,
                "chunk_size": chunk_size,
                "overlap": overlap,
                "params": params or {},
            },
        )

    async def get_or_create_embedding_profile(
        self,
        *,
        name: str,
        component_version_id: uuid.UUID,
        modality: str = "text",
        dimensions: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> EmbeddingProfile:
        """Return the embedding profile for an embedder configuration."""
        return await self._get_or_create(
            EmbeddingProfile,
            component_version_id=component_version_id,
            name=name,
            columns={
                "modality": modality,
                "dimensions": dimensions,
                "params": params or {},
            },
        )

    async def get_or_create_vector_store_profile(
        self,
        *,
        name: str,
        component_version_id: uuid.UUID,
        index_params: dict[str, Any] | None = None,
    ) -> VectorStoreProfile:
        """Return the vector store profile for an index configuration."""
        return await self._get_or_create(
            VectorStoreProfile,
            component_version_id=component_version_id,
            name=name,
            columns={"index_params": index_params or {}},
        )

    async def get_or_create_retrieval_profile(
        self, *, name: str, top_k: int, strategy: str, **options: Any
    ) -> RetrievalProfile:
        """Return the retrieval profile for a retrieval configuration.

        Unlike the other profiles this one has no component version of its own: the
        reranker is the only component it may reference, and it is part of `options` as
        `reranker_version_id`.

        Args:
            name: Readable label, excluded from the hash.
            top_k: Number of results returned.
            strategy: dense / sparse / hybrid / multi_vector.
            **options: Any other column of `retrieval_profiles`, e.g. `pre_rerank_k`,
                `fusion_weights`, `mmr`, `score_threshold`, `metadata_filters`,
                `query_transforms`, `reranker_version_id`, `context_policy`.

        Returns:
            The existing profile with this configuration, or the newly created one.
        """
        columns: dict[str, Any] = {"top_k": top_k, "strategy": strategy, **options}
        hashed = {
            key: str(value) if isinstance(value, uuid.UUID) else value
            for key, value in columns.items()
        }
        digest = hash_json(hashed)
        repository = ProfileRepository(self.session, RetrievalProfile)

        async def create() -> RetrievalProfile:
            profile = repository.add(
                RetrievalProfile(name=name, config_hash=digest, **columns)
            )
            await self.session.flush()
            return profile

        return await get_or_create(
            self.session,
            lookup=lambda: repository.get_by_config_hash(digest),
            create=create,
        )

    async def _get_or_create(
        self,
        model: type[Any],
        *,
        component_version_id: uuid.UUID,
        name: str,
        columns: dict[str, Any],
    ) -> Any:
        """Shared get-or-create for the profile tables.

        The hash covers the component version and **every** behavioural column, including
        the ones promoted out of `params` such as strategy, chunk size, overlap and
        modality. `name` is deliberately excluded: two profiles that behave identically
        must share one row even if the user labelled them differently, otherwise the cache
        would be bypassed by a rename.
        """
        digest = config_hash(component_version_id, columns)
        repository = ProfileRepository(self.session, model)

        async def create() -> Any:
            profile = repository.add(
                model(
                    name=name,
                    component_version_id=component_version_id,
                    config_hash=digest,
                    **columns,
                )
            )
            await self.session.flush()
            return profile

        return await get_or_create(
            self.session,
            lookup=lambda: repository.get_by_config_hash(digest),
            create=create,
        )

    async def _assert_document_scope(self, component_version_id: uuid.UUID) -> None:
        """Reject chunkers whose declared scope is not `document`."""
        version = await self.session.get(ComponentVersion, component_version_id)
        if version is None:
            raise ProfileNotFoundError("chunker component version", component_version_id)
        scope = version.capabilities.get("scope", SUPPORTED_CHUNKER_SCOPE)
        if scope != SUPPORTED_CHUNKER_SCOPE:
            raise UnsupportedChunkerScopeError(scope)


class ChunkingConfigurationService:
    """The (parsing, chunking) pair that chunk-level gold is anchored to (§3.1)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.configurations = ChunkingConfigurationRepository(session)
        self.parsing_profiles = ProfileRepository(session, ParsingProfile)
        self.chunking_profiles = ProfileRepository(session, ChunkingProfile)

    async def get_or_create(
        self,
        *,
        parsing_profile_id: uuid.UUID,
        chunking_profile_id: uuid.UUID,
        name: str | None = None,
    ) -> ChunkingConfiguration:
        """Return the configuration for a profile pair, creating it once.

        Args:
            parsing_profile_id: Parsing profile of the pair.
            chunking_profile_id: Chunking profile of the pair.
            name: Readable label; defaults to `<parsing> + <chunking>`.

        Returns:
            The existing configuration for the pair, or the newly created one.

        Raises:
            ProfileNotFoundError: If either profile does not exist.
        """
        parsing = await self.parsing_profiles.get_by_id(parsing_profile_id)
        if parsing is None:
            raise ProfileNotFoundError("parsing", parsing_profile_id)
        chunking = await self.chunking_profiles.get_by_id(chunking_profile_id)
        if chunking is None:
            raise ProfileNotFoundError("chunking", chunking_profile_id)

        digest = combined_config_hash(parsing.config_hash, chunking.config_hash)
        label = name or f"{parsing.name} + {chunking.name}"

        async def create() -> ChunkingConfiguration:
            configuration = self.configurations.add(
                ChunkingConfiguration(
                    name=label,
                    parsing_profile_id=parsing_profile_id,
                    chunking_profile_id=chunking_profile_id,
                    config_hash=digest,
                )
            )
            await self.session.flush()
            return configuration

        return await get_or_create(
            self.session,
            lookup=lambda: self.configurations.get_by_config_hash(digest),
            create=create,
        )


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
        self, parsing_result: ParsingResult, *, output_uri: str
    ) -> ParsingResult:
        """Mark a parse as `ready` with the storage reference of its output (RT-O02)."""
        parsing_result.output_uri = output_uri
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
            raise ProfileNotFoundError("chunking configuration", chunking_configuration_id)

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


class IndexBuildService:
    """The vector DB population configuration."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.builds = IndexBuildRepository(session)
        self.snapshots = CorpusSnapshotRepository(session)
        self.configurations = ChunkingConfigurationRepository(session)
        self.embedding_profiles = ProfileRepository(session, EmbeddingProfile)
        self.vector_store_profiles = ProfileRepository(session, VectorStoreProfile)

    async def get_or_create(
        self,
        *,
        corpus_snapshot_id: uuid.UUID,
        chunking_configuration_id: uuid.UUID,
        embedding_profile_id: uuid.UUID,
        vector_store_profile_id: uuid.UUID,
        name: str | None = None,
        external_index_ref: str | None = None,
    ) -> IndexBuild:
        """Return the index build for a whole population chain, creating it once.

        The fingerprint covers snapshot composition, chunking configuration, embedder and
        vector store, i.e. everything the content of the index depends on, so repeating
        the same choice rebuilds nothing and stays comparable with what was measured
        before.

        Returns:
            The existing build with this fingerprint, or the newly created one.

        Raises:
            ProfileNotFoundError: If any referenced entity does not exist.
        """
        snapshot = await self.snapshots.get_by_id(corpus_snapshot_id)
        if snapshot is None:
            raise ProfileNotFoundError("corpus snapshot", corpus_snapshot_id)
        configuration = await self.configurations.get_by_id(chunking_configuration_id)
        if configuration is None:
            raise ProfileNotFoundError("chunking configuration", chunking_configuration_id)
        embedding = await self.embedding_profiles.get_by_id(embedding_profile_id)
        if embedding is None:
            raise ProfileNotFoundError("embedding", embedding_profile_id)
        vector_store = await self.vector_store_profiles.get_by_id(vector_store_profile_id)
        if vector_store is None:
            raise ProfileNotFoundError("vector store", vector_store_profile_id)

        fingerprint = chain_fingerprint(
            snapshot.composition_hash,
            configuration.config_hash,
            embedding.config_hash,
            vector_store.config_hash,
        )
        label = name or f"{snapshot.label} · {configuration.name} · {embedding.name}"

        async def create() -> IndexBuild:
            build = self.builds.add(
                IndexBuild(
                    name=label,
                    corpus_snapshot_id=corpus_snapshot_id,
                    chunking_configuration_id=chunking_configuration_id,
                    embedding_profile_id=embedding_profile_id,
                    vector_store_profile_id=vector_store_profile_id,
                    chain_fingerprint=fingerprint,
                    external_index_ref=external_index_ref or f"idx_{fingerprint[:16]}",
                )
            )
            await self.session.flush()
            return build

        return await get_or_create(
            self.session,
            lookup=lambda: self.builds.get_by_chain_fingerprint(fingerprint),
            create=create,
        )


class MaterializationRunService:
    """The denormalised progress of a user-triggered chunk materialisation (RT-O07)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.runs = MaterializationRunRepository(session)

    async def open_run(
        self,
        *,
        workflow_id: str,
        chunking_configuration_id: uuid.UUID,
        document_count: int,
        corpus_id: uuid.UUID | None = None,
    ) -> MaterializationRun:
        """Return the run for a workflow id, creating it as `running` if absent.

        Get-or-create on `workflow_id` so a workflow retried or continued-as-new reuses the
        same row instead of forking the progress the UI reads. An existing row is returned
        untouched: its progress is authoritative for what already happened.
        """

        async def create() -> MaterializationRun:
            run = self.runs.add(
                MaterializationRun(
                    workflow_id=workflow_id,
                    chunking_configuration_id=chunking_configuration_id,
                    corpus_id=corpus_id,
                    document_count=document_count,
                    status=ArtifactStatus.RUNNING,
                    progress={"ready": 0, "failed": 0, "cached": 0, "pending": document_count},
                    started_at=dt.datetime.now(dt.UTC),
                )
            )
            await self.session.flush()
            return run

        return await get_or_create(
            self.session,
            lookup=lambda: self.runs.get_by_workflow_id(workflow_id),
            create=create,
        )

    async def update_progress(
        self, *, workflow_id: str, progress: dict[str, int]
    ) -> MaterializationRun | None:
        """Overwrite a run's progress counters with the workflow's current tally.

        The workflow owns the counts and passes the whole tally each time, so the write is
        idempotent and stays monotonic as long as the caller only ever grows them; `pending`
        is derived so the four numbers always sum to `document_count`.
        """
        run = await self.runs.get_by_workflow_id(workflow_id)
        if run is None:
            return None
        done = progress.get("ready", 0) + progress.get("failed", 0) + progress.get("cached", 0)
        run.progress = {
            "ready": progress.get("ready", 0),
            "failed": progress.get("failed", 0),
            "cached": progress.get("cached", 0),
            "pending": max(run.document_count - done, 0),
        }
        await self.session.flush()
        return run

    async def complete_run(
        self, *, workflow_id: str, progress: dict[str, int]
    ) -> MaterializationRun | None:
        """Mark a run finished with its final tally, `ready` unless any document failed."""
        run = await self.update_progress(workflow_id=workflow_id, progress=progress)
        if run is None:
            return None
        run.status = (
            ArtifactStatus.FAILED if run.progress["failed"] else ArtifactStatus.READY
        )
        run.finished_at = dt.datetime.now(dt.UTC)
        await self.session.flush()
        return run
