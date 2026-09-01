from __future__ import annotations

import asyncio
import dataclasses
import datetime as dt
import json
import logging
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.components.models import ComponentVersion
from src.components.service import ComponentService
from src.core.get_or_create import get_or_create, get_or_create_reporting
from src.core.hashing import (
    cache_key,
    chain_fingerprint,
    combined_config_hash,
    config_hash,
    hash_json,
)
from src.corpora.repository import CorpusDocumentRepository, CorpusSnapshotRepository
from src.corpora.service import CorpusService
from src.documents.exceptions import DocumentNotFoundError
from src.documents.repository import DocumentRepository
from src.infrastructure.database.enums import ArtifactStatus, DocumentStatus
from src.infrastructure.storage import ObjectStorage, storage_key
from src.infrastructure.temporal import WorkflowClient
from src.pipelines.exceptions import (
    ChunkingConfigurationNotFoundError,
    ChunkNotFoundError,
    ChunkResultNotFoundError,
    DocumentsNotStoredError,
    EmptyMaterializationError,
    MaterializationNotCancellableError,
    MaterializationRunNotFoundError,
    ParsingProfileMismatchError,
    ParsingResultNotFoundError,
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
from src.pipelines.workflow_ids import (
    CHUNKING_TASK_QUEUE,
    MATERIALIZE_CHUNKS_WORKFLOW,
    materialize_workflow_id,
)

logger = logging.getLogger(__name__)

SUPPORTED_CHUNKER_SCOPE = "document"


class ProfileService:
    """Creation of pipeline profiles, deduplicated by `config_hash`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.components = ComponentService(session)

    async def get_or_create_parsing_profile(
        self, *, name: str, component_version_id: uuid.UUID, params: dict[str, Any] | None = None
    ) -> tuple[ParsingProfile, bool]:
        """Return the parsing profile for a (component version, params) pair.

        Returns:
            The profile and whether this call created it.

        Raises:
            InvalidComponentParamsError: If the parameters violate the version's schema.
            ComponentVersionNotFoundError: If the component version does not exist.
        """
        await self.components.validate_params(component_version_id, params or {})
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
    ) -> tuple[ChunkingProfile, bool]:
        """Return the chunking profile for a chunker configuration.

        `chunk_size` and `overlap` are folded into the parameters that are validated, since
        they are promoted columns of the same contract the schema describes: validating only
        `params` would let an out-of-range chunk size through to the worker.

        Returns:
            The profile and whether this call created it.

        Raises:
            UnsupportedChunkerScopeError: If the component version declares a scope other
                than `document`.
            ProfileNotFoundError: If the component version does not exist.
            InvalidComponentParamsError: If the parameters violate the version's schema.
        """
        await self._assert_document_scope(component_version_id)
        await self.components.validate_params(
            component_version_id,
            _effective_chunker_params(params, chunk_size=chunk_size, overlap=overlap),
        )
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
    ) -> tuple[EmbeddingProfile, bool]:
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
    ) -> tuple[VectorStoreProfile, bool]:
        """Return the vector store profile for an index configuration."""
        return await self._get_or_create(
            VectorStoreProfile,
            component_version_id=component_version_id,
            name=name,
            columns={"index_params": index_params or {}},
        )

    async def get_parsing_profile(self, profile_id: uuid.UUID) -> ParsingProfile:
        """Return a parsing profile by id.

        Raises:
            ProfileNotFoundError: If it does not exist.
        """
        profile = await ProfileRepository(self.session, ParsingProfile).get_by_id(profile_id)
        if profile is None:
            raise ProfileNotFoundError("parsing", profile_id)
        return profile

    async def get_chunking_profile(self, profile_id: uuid.UUID) -> ChunkingProfile:
        """Return a chunking profile by id.

        Raises:
            ProfileNotFoundError: If it does not exist.
        """
        profile = await ProfileRepository(self.session, ChunkingProfile).get_by_id(profile_id)
        if profile is None:
            raise ProfileNotFoundError("chunking", profile_id)
        return profile

    async def list_parsing_profiles(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[ParsingProfile], int]:
        """One page of parsing profiles and the size of the whole set."""
        repository = ProfileRepository(self.session, ParsingProfile)
        return await repository.list(limit=limit, offset=offset), await repository.count()

    async def list_chunking_profiles(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[ChunkingProfile], int]:
        """One page of chunking profiles and the size of the whole set."""
        repository = ProfileRepository(self.session, ChunkingProfile)
        return await repository.list(limit=limit, offset=offset), await repository.count()

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
    ) -> tuple[Any, bool]:
        """Shared get-or-create for the profile tables.

        The hash covers the component version and **every** behavioural column, including
        the ones promoted out of `params` such as strategy, chunk size, overlap and
        modality. `name` is deliberately excluded: two profiles that behave identically
        must share one row even if the user labelled them differently, otherwise the cache
        would be bypassed by a rename. The returned flag is what lets the caller say so,
        instead of leaving the user to wonder where their name went.
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

        return await get_or_create_reporting(
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


def _effective_chunker_params(
    params: dict[str, Any] | None, *, chunk_size: int | None, overlap: int | None
) -> dict[str, Any]:
    """Fold the promoted columns back into the params a chunker schema describes.

    Mirrors what the worker does when it loads a profile, so validation at the API boundary
    sees exactly the parameters the chunker will receive.
    """
    effective = dict(params or {})
    if chunk_size is not None:
        effective.setdefault("chunk_size", chunk_size)
    if overlap is not None:
        effective.setdefault("overlap", overlap)
    return effective


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


@dataclasses.dataclass(frozen=True)
class ExpandedConfiguration:
    """A configuration together with the two profiles it is made of.

    Returned as one object because the UI shows "pypdf + recursive512" as a label: resolving
    it client-side would cost three calls to render one row.
    """

    configuration: ChunkingConfiguration
    parsing_profile: ParsingProfile
    chunking_profile: ChunkingProfile


@dataclasses.dataclass(frozen=True)
class ComposedConfiguration:
    """The result of composing a configuration from two profiles given by value."""

    expanded: ExpandedConfiguration
    parsing_profile_created: bool
    chunking_profile_created: bool
    configuration_created: bool


class ChunkingConfigurationService:
    """The (parsing, chunking) pair that chunk-level gold is anchored to."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.configurations = ChunkingConfigurationRepository(session)
        self.parsing_profiles = ProfileRepository(session, ParsingProfile)
        self.chunking_profiles = ProfileRepository(session, ChunkingProfile)
        self.chunk_results = ChunkResultRepository(session)
        self.corpus_documents = CorpusDocumentRepository(session)

    async def get_or_create(
        self,
        *,
        parsing_profile_id: uuid.UUID,
        chunking_profile_id: uuid.UUID,
        name: str | None = None,
    ) -> tuple[ChunkingConfiguration, bool]:
        """Return the configuration for a profile pair, creating it once.

        Args:
            parsing_profile_id: Parsing profile of the pair.
            chunking_profile_id: Chunking profile of the pair.
            name: Readable label; defaults to `<parsing> + <chunking>`.

        Returns:
            The configuration for the pair and whether this call created it.

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

        return await get_or_create_reporting(
            self.session,
            lookup=lambda: self.configurations.get_by_config_hash(digest),
            create=create,
        )

    async def get(self, configuration_id: uuid.UUID) -> ChunkingConfiguration:
        """Return a configuration by id.

        Raises:
            ChunkingConfigurationNotFoundError: If it does not exist.
        """
        configuration = await self.configurations.get_by_id(configuration_id)
        if configuration is None:
            raise ChunkingConfigurationNotFoundError(configuration_id)
        return configuration

    async def expand(self, configuration: ChunkingConfiguration) -> ExpandedConfiguration:
        """Resolve the two profiles of a configuration.

        Raises:
            ProfileNotFoundError: If either profile is missing, which the `RESTRICT` foreign
                keys make impossible in practice.
        """
        parsing = await self.parsing_profiles.get_by_id(configuration.parsing_profile_id)
        if parsing is None:
            raise ProfileNotFoundError("parsing", configuration.parsing_profile_id)
        chunking = await self.chunking_profiles.get_by_id(configuration.chunking_profile_id)
        if chunking is None:
            raise ProfileNotFoundError("chunking", configuration.chunking_profile_id)
        return ExpandedConfiguration(
            configuration=configuration,
            parsing_profile=parsing,
            chunking_profile=chunking,
        )

    async def list_expanded(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[ExpandedConfiguration], int]:
        """One page of configurations with their profiles resolved, and the total."""
        configurations = await self.configurations.list(limit=limit, offset=offset)
        expanded = [await self.expand(configuration) for configuration in configurations]
        return expanded, await self.configurations.count()

    async def compose(
        self,
        *,
        parsing_component_version_id: uuid.UUID,
        parsing_params: dict[str, Any] | None = None,
        parsing_profile_name: str,
        chunking_component_version_id: uuid.UUID,
        chunking_strategy: str,
        chunk_size: int | None = None,
        overlap: int | None = None,
        chunking_params: dict[str, Any] | None = None,
        chunking_profile_name: str,
        name: str | None = None,
    ) -> ComposedConfiguration:
        """Create both profiles and their configuration in one act.

        The shortcut behind a single UI form: three get-or-creates in one transaction, so a
        half-composed configuration cannot be left behind if the second profile is rejected.
        The granular endpoints remain, since anything that reuses an existing profile should
        reference it by id rather than restate it by value.

        Returns:
            The expanded configuration and which of the three rows this call created.
        """
        profiles = ProfileService(self.session)
        parsing, parsing_created = await profiles.get_or_create_parsing_profile(
            name=parsing_profile_name,
            component_version_id=parsing_component_version_id,
            params=parsing_params,
        )
        chunking, chunking_created = await profiles.get_or_create_chunking_profile(
            name=chunking_profile_name,
            component_version_id=chunking_component_version_id,
            strategy=chunking_strategy,
            chunk_size=chunk_size,
            overlap=overlap,
            params=chunking_params,
        )
        configuration, configuration_created = await self.get_or_create(
            parsing_profile_id=parsing.id,
            chunking_profile_id=chunking.id,
            name=name,
        )
        return ComposedConfiguration(
            expanded=ExpandedConfiguration(
                configuration=configuration,
                parsing_profile=parsing,
                chunking_profile=chunking,
            ),
            parsing_profile_created=parsing_created,
            chunking_profile_created=chunking_created,
            configuration_created=configuration_created,
        )

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
        await self.get(configuration_id)
        await CorpusService(self.session).get(corpus_id)

        document_ids = await self.corpus_documents.list_document_ids(corpus_id)
        by_status = await self.chunk_results.count_by_status(document_ids, configuration_id)
        ready = by_status.get(ArtifactStatus.READY, 0)
        failed = by_status.get(ArtifactStatus.FAILED, 0)
        total = len(document_ids)
        return ConfigurationCoverage(
            total=total,
            ready=ready,
            failed=failed,
            missing=max(total - ready - failed, 0),
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


# Default child-workflow concurrency of a run; mirrors the workflow's own default so the API
# and the worker cannot disagree about what "no concurrency given" means.
DEFAULT_MATERIALIZATION_CONCURRENCY = 5

# Upper bound on the failures reported with a run: the list explains a failure, it is not a
# report, and the per-document detail is always available from the chunk-result endpoints.
_MAX_REPORTED_FAILURES = 50

CANCELLED_REASON = "cancelled"

# A run that reached one of these is over: relaunching the same work reopens the row, and
# cancelling it is refused.
TERMINAL_ARTIFACT_STATUSES = (ArtifactStatus.READY, ArtifactStatus.FAILED)


@dataclasses.dataclass(frozen=True)
class DocumentFailure:
    """Why one document of a run did not produce chunks."""

    document_id: uuid.UUID
    error: str | None


@dataclasses.dataclass(frozen=True)
class MaterializationLaunch:
    """A launched materialisation and whether this request is what started it."""

    run: MaterializationRun
    started: bool


class MaterializationRunService:
    """The denormalised progress of a user-triggered chunk materialisation (RT-O07).

    Reads and writes the run row and the artefacts it summarises, and nothing else:
    following a run must not depend on Temporal being reachable, which is the whole reason
    the row exists.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.runs = MaterializationRunRepository(session)
        self.chunk_results = ChunkResultRepository(session)
        self.corpus_documents = CorpusDocumentRepository(session)

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
        same row instead of forking the progress the UI reads: a run still in flight is
        returned untouched, because its progress is authoritative for what already happened.

        A row that already reached a terminal state is reset instead. The workflow id is a
        function of the configuration and the document set, so relaunching the same work
        after a failure or a cancellation lands on the same row; leaving it terminal would
        show `cancelled` while a new workflow is running.
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

        run = await get_or_create(
            self.session,
            lookup=lambda: self.runs.get_by_workflow_id(workflow_id),
            create=create,
        )
        if run.status in TERMINAL_ARTIFACT_STATUSES:
            run.status = ArtifactStatus.RUNNING
            run.document_count = document_count
            run.progress = {"ready": 0, "failed": 0, "cached": 0, "pending": document_count}
            run.error = None
            run.started_at = dt.datetime.now(dt.UTC)
            run.finished_at = None
            await self.session.flush()
        return run

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

    async def get(self, run_id: uuid.UUID) -> MaterializationRun:
        """Return a run by id.

        Raises:
            MaterializationRunNotFoundError: If it does not exist.
        """
        run = await self.runs.get_by_id(run_id)
        if run is None:
            raise MaterializationRunNotFoundError(run_id)
        return run

    async def list(
        self,
        *,
        corpus_id: uuid.UUID | None = None,
        chunking_configuration_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[MaterializationRun], int]:
        """One page of run history, newest first, and the size of the whole set."""
        runs = await self.runs.list(
            corpus_id=corpus_id,
            chunking_configuration_id=chunking_configuration_id,
            limit=limit,
            offset=offset,
        )
        total = await self.runs.count(
            corpus_id=corpus_id, chunking_configuration_id=chunking_configuration_id
        )
        return runs, total

    async def failures(self, run: MaterializationRun) -> list[DocumentFailure]:
        """Documents that failed under the run's configuration, with their reason.

        Read from `chunk_results` and not from a column of the run: the outcome of a document
        is a property of its artefact, and duplicating it here would create a second
        truth that a re-materialisation would leave stale. When the run has a corpus the list
        is scoped to it; a run launched on explicit ids is a preview of a few files, so the
        configuration's failures are the same set in practice.
        """
        document_ids = (
            await self.corpus_documents.list_document_ids(run.corpus_id)
            if run.corpus_id is not None
            else None
        )
        failed = await self.chunk_results.list_failed(
            run.chunking_configuration_id,
            document_ids=document_ids,
            limit=_MAX_REPORTED_FAILURES,
        )
        return [
            DocumentFailure(document_id=result.document_id, error=result.error)
            for result in failed
        ]


class MaterializationService:
    """Launch and cancel a chunk materialisation over a set of documents.

    The same entry point serves the preview on a handful of files (RF-P08) and a whole
    corpus, exactly as the same workflow does: the difference is the size of the document
    list, not the code path, so what the user previews is what the corpus run will produce.
    Reading a run's progress belongs to `MaterializationRunService`, which needs no Temporal
    connection.
    """

    def __init__(self, session: AsyncSession, workflows: WorkflowClient) -> None:
        self.session = session
        self.workflows = workflows
        self.runs = MaterializationRunService(session)
        self.configurations = ChunkingConfigurationService(session)
        self.documents = DocumentRepository(session)
        self.corpus_documents = CorpusDocumentRepository(session)

    async def start(
        self,
        *,
        chunking_configuration_id: uuid.UUID,
        document_ids: Sequence[uuid.UUID] | None = None,
        corpus_id: uuid.UUID | None = None,
        concurrency: int | None = None,
    ) -> MaterializationLaunch:
        """Start a materialisation, or return the run already doing the same work.

        The workflow id is a function of the configuration and the document *set*, so a
        second identical request is refused by Temporal itself and reported as the existing
        run: a double click on the launch button is not a user error (RT-O01).

        Args:
            chunking_configuration_id: Configuration to materialise.
            document_ids: Explicit documents; when omitted, every document of `corpus_id`.
            corpus_id: Corpus the run belongs to, recorded for the UI and used to resolve the
                documents when none are given explicitly.
            concurrency: Maximum number of documents processed at once.

        Returns:
            The run row and whether this call started the workflow.

        Raises:
            ChunkingConfigurationNotFoundError: If the configuration does not exist.
            CorpusNotFoundError: If `corpus_id` does not exist.
            EmptyMaterializationError: If no document was resolved.
            DocumentsNotStoredError: If any resolved document is not `stored`.
        """
        await self.configurations.get(chunking_configuration_id)
        resolved = await self._resolve_documents(document_ids, corpus_id)

        workflow_id = materialize_workflow_id(chunking_configuration_id, resolved)
        run = await self.runs.open_run(
            workflow_id=workflow_id,
            chunking_configuration_id=chunking_configuration_id,
            document_count=len(resolved),
            corpus_id=corpus_id,
        )
        outcome = await self.workflows.start(
            MATERIALIZE_CHUNKS_WORKFLOW,
            arg={
                "document_ids": [str(document_id) for document_id in resolved],
                "chunking_configuration_id": str(chunking_configuration_id),
                "corpus_id": str(corpus_id) if corpus_id else None,
                "max_concurrency": concurrency or DEFAULT_MATERIALIZATION_CONCURRENCY,
            },
            workflow_id=workflow_id,
            task_queue=CHUNKING_TASK_QUEUE,
        )
        return MaterializationLaunch(run=run, started=outcome.started)

    async def cancel(self, run_id: uuid.UUID) -> MaterializationRun:
        """Cancel a running materialisation, recording `cancelled` as its reason.

        Not required by the requirements for chunking (RF-E08 is about experiments), but a
        user who launched a chunking over two hundred wrong files looks for this immediately.

        Raises:
            MaterializationRunNotFoundError: If the run does not exist.
            MaterializationNotCancellableError: If the run already reached a terminal state.
        """
        run = await self.runs.get(run_id)
        if run.status in TERMINAL_ARTIFACT_STATUSES:
            raise MaterializationNotCancellableError(run_id, run.status)

        await self.workflows.cancel(run.workflow_id)
        # Marked terminal here rather than waiting for the workflow's own summary activity:
        # a cancelled workflow may never run one, and a run stuck on `running` forever is
        # worse than one that says it was cancelled.
        run.status = ArtifactStatus.FAILED
        run.error = CANCELLED_REASON
        run.finished_at = dt.datetime.now(dt.UTC)
        await self.session.flush()
        return run

    async def _resolve_documents(
        self, document_ids: Sequence[uuid.UUID] | None, corpus_id: uuid.UUID | None
    ) -> list[uuid.UUID]:
        """Resolve and validate the document set a run will cover.

        Every document must be `stored`: parsing something still being fetched would produce
        an artefact keyed on a content hash that is not final yet.
        """
        if document_ids:
            resolved = list(dict.fromkeys(document_ids))
        else:
            if corpus_id is None:
                raise EmptyMaterializationError()
            await CorpusService(self.session).get(corpus_id)
            resolved = list(await self.corpus_documents.list_document_ids(corpus_id))

        if not resolved:
            raise EmptyMaterializationError()

        found = await self.documents.list_by_ids(resolved)
        by_id = {document.id: document for document in found}
        offending = {
            str(document_id): (
                by_id[document_id].status.value if document_id in by_id else "unknown"
            )
            for document_id in resolved
            if document_id not in by_id or by_id[document_id].status is not DocumentStatus.STORED
        }
        if offending:
            raise DocumentsNotStoredError(offending)
        return resolved


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
        chunks = await self.chunks.list_by_chunk_result(result.id, limit=limit, offset=offset)
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
