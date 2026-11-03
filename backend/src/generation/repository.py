from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.artifacts.models import Chunk, ChunkResult, ParsingResult
from src.corpora.models import CorpusDocument
from src.documents.models import Document
from src.generation.models import (
    GeneratedQuestion,
    GeneratedQuestionChunk,
    GenerationJob,
    GenerationUnit,
)
from src.infrastructure.database.enums import (
    ArtifactStatus,
    ExecutionStatus,
    GeneratedKind,
    GenerationPhase,
    ProposalStatus,
)
from src.transfers.matching import tokens

# Characters of a chunk shown in an outline row, and of a document in the catalogue when
# the document phase left no summary.
_OUTLINE_CHARS = 120
_HEAD_CHARS = 200


@dataclasses.dataclass(frozen=True)
class CorpusDocumentState:
    """A document of a corpus and whether it can be read under a configuration."""

    document_id: uuid.UUID
    filename: str
    materialised: bool


@dataclasses.dataclass(frozen=True)
class CatalogueRow:
    """A document as the agent's catalogue lists it."""

    document_id: uuid.UUID
    filename: str
    text_length: int
    chunk_count: int
    head: str


@dataclasses.dataclass(frozen=True)
class ChunkRow:
    """A chunk with its document, as the tools and the review read it."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    ordinal: int
    page: int | None
    text: str


@dataclasses.dataclass(frozen=True)
class ProposalChunkRow:
    """A chunk cited by a proposal, with what the reviewer reads of it."""

    link: GeneratedQuestionChunk
    chunk: ChunkRow


def _page(metadata: dict | None) -> int | None:
    page = (metadata or {}).get("page")
    return page if isinstance(page, int) else None


def _chunk_row(chunk: Chunk, document_id: uuid.UUID, filename: str) -> ChunkRow:
    return ChunkRow(
        chunk_id=chunk.id,
        document_id=document_id,
        filename=filename,
        ordinal=chunk.ordinal,
        page=_page(chunk.chunk_metadata),
        text=chunk.text,
    )


class GenerationJobRepository:
    """Data access for `generation_jobs`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, job: GenerationJob) -> GenerationJob:
        self.session.add(job)
        return job

    async def get_by_id(self, generation_job_id: uuid.UUID) -> GenerationJob | None:
        return await self.session.get(GenerationJob, generation_job_id)

    async def list(
        self, *, qa_set_id: uuid.UUID | None, limit: int, offset: int
    ) -> Sequence[GenerationJob]:
        stmt = select(GenerationJob).order_by(
            GenerationJob.created_at.desc(), GenerationJob.id.desc()
        )
        if qa_set_id is not None:
            stmt = stmt.where(GenerationJob.qa_set_id == qa_set_id)
        return (await self.session.scalars(stmt.limit(limit).offset(offset))).all()

    async def count(self, *, qa_set_id: uuid.UUID | None) -> int:
        stmt = select(func.count()).select_from(GenerationJob)
        if qa_set_id is not None:
            stmt = stmt.where(GenerationJob.qa_set_id == qa_set_id)
        return await self.session.scalar(stmt) or 0


class GenerationUnitRepository:
    """Data access for `generation_units`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_all(self, units: Sequence[GenerationUnit]) -> None:
        self.session.add_all(units)

    async def get_by_id(self, unit_id: uuid.UUID) -> GenerationUnit | None:
        return await self.session.get(GenerationUnit, unit_id)

    async def list_by_job(self, generation_job_id: uuid.UUID) -> list[GenerationUnit]:
        """The units of a job, the document phase first, each phase in its order."""
        stmt = (
            select(GenerationUnit)
            .where(GenerationUnit.generation_job_id == generation_job_id)
            .order_by(GenerationUnit.phase, GenerationUnit.position)
        )
        return list((await self.session.scalars(stmt)).all())

    async def unfinished_ids(
        self,
        generation_job_id: uuid.UUID,
        phase: GenerationPhase,
        *,
        after_position: int | None,
        limit: int,
    ) -> list[uuid.UUID]:
        """One page of the units of a phase not done yet, in order, after a cursor."""
        stmt = select(GenerationUnit.id).where(
            GenerationUnit.generation_job_id == generation_job_id,
            GenerationUnit.phase == phase,
            GenerationUnit.status != ExecutionStatus.SUCCEEDED,
        )
        if after_position is not None:
            stmt = stmt.where(GenerationUnit.position > after_position)
        stmt = stmt.order_by(GenerationUnit.position).limit(limit)
        return list((await self.session.scalars(stmt)).all())

    async def reset_running(self, generation_job_id: uuid.UUID) -> None:
        """Put units an interrupted attempt left `running` back to `pending`."""
        await self.session.execute(
            update(GenerationUnit)
            .where(
                GenerationUnit.generation_job_id == generation_job_id,
                GenerationUnit.status == ExecutionStatus.RUNNING,
            )
            .values(status=ExecutionStatus.PENDING)
        )


class ProposalRepository:
    """Data access for `generated_questions` and the chunks they cite."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self, proposal: GeneratedQuestion, chunks: Sequence[GeneratedQuestionChunk]
    ) -> GeneratedQuestion:
        self.session.add(proposal)
        await self.session.flush()
        for chunk in chunks:
            chunk.generated_question_id = proposal.id
        self.session.add_all(chunks)
        await self.session.flush()
        return proposal

    async def get_by_id(self, proposal_id: uuid.UUID) -> GeneratedQuestion | None:
        return await self.session.get(GeneratedQuestion, proposal_id)

    async def get_for_update(self, proposal_id: uuid.UUID) -> GeneratedQuestion | None:
        """A proposal locked for the rest of the transaction, so two decisions serialise."""
        stmt = (
            select(GeneratedQuestion)
            .where(GeneratedQuestion.id == proposal_id)
            .with_for_update()
        )
        return await self.session.scalar(stmt)

    async def texts(
        self,
        generation_job_id: uuid.UUID,
        *,
        unit_id: uuid.UUID | None = None,
        phase: GenerationPhase | None = None,
    ) -> list[str]:
        """Texts of the proposals not rejected, of a job or one of its units or phases."""
        stmt = select(GeneratedQuestion.text).where(
            GeneratedQuestion.generation_job_id == generation_job_id,
            GeneratedQuestion.status != ProposalStatus.REJECTED,
        )
        if unit_id is not None:
            stmt = stmt.where(GeneratedQuestion.unit_id == unit_id)
        if phase is not None:
            stmt = stmt.join(
                GenerationUnit, GenerationUnit.id == GeneratedQuestion.unit_id
            ).where(GenerationUnit.phase == phase)
        stmt = stmt.order_by(GeneratedQuestion.created_at, GeneratedQuestion.id)
        return list((await self.session.scalars(stmt)).all())

    async def count_by_unit(self, unit_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(GeneratedQuestion.unit_id == unit_id)
        return await self.session.scalar(stmt) or 0

    async def list(
        self,
        generation_job_id: uuid.UUID,
        *,
        status: ProposalStatus | None,
        kind: GeneratedKind | None,
        limit: int,
        offset: int,
    ) -> tuple[list[GeneratedQuestion], int]:
        """One page of the proposals of a job in the order they were saved, and the total."""
        conditions = [GeneratedQuestion.generation_job_id == generation_job_id]
        if status is not None:
            conditions.append(GeneratedQuestion.status == status)
        if kind is not None:
            conditions.append(GeneratedQuestion.kind == kind)
        stmt = (
            select(GeneratedQuestion)
            .where(*conditions)
            .order_by(GeneratedQuestion.created_at, GeneratedQuestion.id)
        )
        total = await self.session.scalar(
            select(func.count()).select_from(GeneratedQuestion).where(*conditions)
        )
        rows = (await self.session.scalars(stmt.limit(limit).offset(offset))).all()
        return list(rows), total or 0

    async def next_pending(
        self,
        generation_job_id: uuid.UUID,
        *,
        after: GeneratedQuestion,
        kind: GeneratedKind | None = None,
    ) -> uuid.UUID | None:
        """The next proposal waiting for a decision, after this one or else from the top."""
        conditions = [
            GeneratedQuestion.generation_job_id == generation_job_id,
            GeneratedQuestion.status == ProposalStatus.PENDING,
            GeneratedQuestion.id != after.id,
        ]
        if kind is not None:
            conditions.append(GeneratedQuestion.kind == kind)
        order = (GeneratedQuestion.created_at, GeneratedQuestion.id)
        later = await self.session.scalar(
            select(GeneratedQuestion.id)
            .where(
                *conditions,
                tuple_(*order) > tuple_(after.created_at, after.id),
            )
            .order_by(*order)
            .limit(1)
        )
        if later is not None:
            return later
        return await self.session.scalar(
            select(GeneratedQuestion.id).where(*conditions).order_by(*order).limit(1)
        )

    async def counts(
        self, generation_job_id: uuid.UUID
    ) -> dict[tuple[ProposalStatus, GeneratedKind], int]:
        stmt = (
            select(GeneratedQuestion.status, GeneratedQuestion.kind, func.count())
            .where(GeneratedQuestion.generation_job_id == generation_job_id)
            .group_by(GeneratedQuestion.status, GeneratedQuestion.kind)
        )
        return {
            (status, kind): count
            for status, kind, count in (await self.session.execute(stmt)).all()
        }

    async def chunks_of(
        self, proposal_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[ProposalChunkRow]]:
        """The cited chunks of some proposals, in the order they were cited."""
        if not proposal_ids:
            return {}
        stmt = (
            select(GeneratedQuestionChunk, Chunk, Document.id, Document.filename)
            .join(Chunk, Chunk.id == GeneratedQuestionChunk.chunk_id)
            .join(Document, Document.id == GeneratedQuestionChunk.document_id)
            .where(GeneratedQuestionChunk.generated_question_id.in_(proposal_ids))
            .order_by(
                GeneratedQuestionChunk.generated_question_id,
                GeneratedQuestionChunk.rank,
            )
        )
        result: dict[uuid.UUID, list[ProposalChunkRow]] = {}
        for link, chunk, document_id, filename in (
            await self.session.execute(stmt)
        ).all():
            result.setdefault(link.generated_question_id, []).append(
                ProposalChunkRow(link, _chunk_row(chunk, document_id, filename))
            )
        return result

    async def documents_by_proposal(
        self, generation_job_id: uuid.UUID
    ) -> dict[uuid.UUID, set[uuid.UUID]]:
        """The documents each proposal of a job cites, for its coverage."""
        stmt = (
            select(
                GeneratedQuestionChunk.generated_question_id,
                GeneratedQuestionChunk.document_id,
            )
            .join(
                GeneratedQuestion,
                GeneratedQuestion.id == GeneratedQuestionChunk.generated_question_id,
            )
            .where(
                GeneratedQuestion.generation_job_id == generation_job_id,
                GeneratedQuestion.status != ProposalStatus.REJECTED,
            )
        )
        result: dict[uuid.UUID, set[uuid.UUID]] = {}
        for proposal_id, document_id in (await self.session.execute(stmt)).all():
            result.setdefault(proposal_id, set()).add(document_id)
        return result


class CorpusTextRepository:
    """What the agent reads: the parsed text and the chunks of a job's documents.

    Every query is bound to a chunking configuration and to the documents it is given, so
    a tool can only ever see the documents of its own unit.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def corpus_documents(
        self, corpus_id: uuid.UUID, chunking_configuration_id: uuid.UUID
    ) -> list[CorpusDocumentState]:
        """The documents of a corpus by file name, and whether each can be read.

        A document can be read when its chunks are ready under the configuration and its
        parse kept the text, which is what the agent reads before choosing a chunk.
        """
        ready = (
            select(ChunkResult.document_id)
            .join(ParsingResult, ParsingResult.id == ChunkResult.parsing_result_id)
            .where(
                ChunkResult.chunking_configuration_id == chunking_configuration_id,
                ChunkResult.status == ArtifactStatus.READY,
                ParsingResult.output_text.is_not(None),
            )
        )
        stmt = (
            select(
                Document.id,
                Document.filename,
                Document.id.in_(ready),
            )
            .join(CorpusDocument, CorpusDocument.document_id == Document.id)
            .where(CorpusDocument.corpus_id == corpus_id)
            .order_by(Document.filename, Document.id)
        )
        return [
            CorpusDocumentState(document_id, filename, bool(materialised))
            for document_id, filename, materialised in (
                await self.session.execute(stmt)
            ).all()
        ]

    async def catalogue(
        self, chunking_configuration_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, CatalogueRow]:
        """Name, text length, chunk count and opening of each document, by id."""
        if not document_ids:
            return {}
        stmt = (
            select(
                Document.id,
                Document.filename,
                func.coalesce(func.char_length(ParsingResult.output_text), 0),
                ChunkResult.chunk_count,
                func.coalesce(
                    func.substr(ParsingResult.output_text, 1, _HEAD_CHARS), ""
                ),
            )
            .join(ChunkResult, ChunkResult.document_id == Document.id)
            .join(ParsingResult, ParsingResult.id == ChunkResult.parsing_result_id)
            .where(
                ChunkResult.chunking_configuration_id == chunking_configuration_id,
                Document.id.in_(document_ids),
            )
        )
        return {
            row[0]: CatalogueRow(*row)
            for row in (await self.session.execute(stmt)).all()
        }

    async def text_window(
        self,
        chunking_configuration_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        offset: int,
        length: int,
    ) -> tuple[str, int]:
        """A window of a document's parsed text and its total length.

        Cut by Postgres, so a long document is never loaded whole to show a page of it.
        """
        stmt = (
            select(
                func.substr(ParsingResult.output_text, offset + 1, length),
                func.char_length(ParsingResult.output_text),
            )
            .join(ChunkResult, ChunkResult.parsing_result_id == ParsingResult.id)
            .where(
                ChunkResult.chunking_configuration_id == chunking_configuration_id,
                ChunkResult.document_id == document_id,
            )
        )
        row = (await self.session.execute(stmt)).first()
        if row is None:
            return "", 0
        return row[0] or "", row[1] or 0

    async def outline(
        self,
        chunking_configuration_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        offset: int,
        limit: int,
    ) -> list[tuple[int, int | None, str]]:
        """One page of the chunks of a document: ordinal, page and their opening words."""
        stmt = (
            select(
                Chunk.ordinal,
                Chunk.chunk_metadata,
                func.substr(Chunk.text, 1, _OUTLINE_CHARS),
            )
            .join(ChunkResult, ChunkResult.id == Chunk.chunk_result_id)
            .where(
                ChunkResult.chunking_configuration_id == chunking_configuration_id,
                ChunkResult.document_id == document_id,
            )
            .order_by(Chunk.ordinal)
            .offset(offset)
            .limit(limit)
        )
        return [
            (ordinal, _page(metadata), text)
            for ordinal, metadata, text in (await self.session.execute(stmt)).all()
        ]

    def _chunks(self, chunking_configuration_id: uuid.UUID):
        return (
            select(Chunk, Document.id, Document.filename)
            .join(ChunkResult, ChunkResult.id == Chunk.chunk_result_id)
            .join(Document, Document.id == ChunkResult.document_id)
            .where(ChunkResult.chunking_configuration_id == chunking_configuration_id)
        )

    async def chunks_at(
        self,
        chunking_configuration_id: uuid.UUID,
        positions: Sequence[tuple[uuid.UUID, int]],
    ) -> dict[tuple[uuid.UUID, int], ChunkRow]:
        """The chunks at some (document, ordinal) positions, by position."""
        if not positions:
            return {}
        stmt = self._chunks(chunking_configuration_id).where(
            tuple_(ChunkResult.document_id, Chunk.ordinal).in_(list(positions))
        )
        rows = [_chunk_row(*row) for row in (await self.session.execute(stmt)).all()]
        return {(row.document_id, row.ordinal): row for row in rows}

    async def chunk_range(
        self,
        chunking_configuration_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        first: int,
        last: int,
    ) -> list[ChunkRow]:
        """The chunks of a document from one ordinal to another, both included."""
        stmt = (
            self._chunks(chunking_configuration_id)
            .where(
                ChunkResult.document_id == document_id,
                Chunk.ordinal.between(first, last),
            )
            .order_by(Chunk.ordinal)
        )
        return [_chunk_row(*row) for row in (await self.session.execute(stmt)).all()]

    async def document_chunks(
        self, chunking_configuration_id: uuid.UUID, document_id: uuid.UUID
    ) -> list[ChunkRow]:
        """Every chunk of a document, in reading order."""
        stmt = (
            self._chunks(chunking_configuration_id)
            .where(ChunkResult.document_id == document_id)
            .order_by(Chunk.ordinal)
        )
        return [_chunk_row(*row) for row in (await self.session.execute(stmt)).all()]

    async def chunks_by_id(
        self, chunking_configuration_id: uuid.UUID, chunk_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, ChunkRow]:
        """Some chunks of a configuration by id; ids of other configurations are absent."""
        if not chunk_ids:
            return {}
        stmt = self._chunks(chunking_configuration_id).where(Chunk.id.in_(chunk_ids))
        rows = [_chunk_row(*row) for row in (await self.session.execute(stmt)).all()]
        return {row.chunk_id: row for row in rows}

    async def search(
        self,
        chunking_configuration_id: uuid.UUID,
        document_ids: Sequence[uuid.UUID],
        query: str,
        *,
        limit: int,
    ) -> list[ChunkRow]:
        """The chunks of some documents most relevant to a query in natural language.

        Postgres full text with the `simple` dictionary, so no language has to be set,
        and any word of the query is enough, ranked by `ts_rank`: the agent searches
        with its own words, which rarely all appear in one chunk. A plain scan over the
        chunks of the documents, without an index.
        """
        # Plain words only: the web search syntax would read a leading dash or a quote
        # as an operator.
        words = tokens(query)
        if not words or not document_ids:
            return []
        tsquery = func.websearch_to_tsquery("simple", " or ".join(words))
        vector = func.to_tsvector("simple", Chunk.text)
        stmt = (
            self._chunks(chunking_configuration_id)
            .where(
                ChunkResult.document_id.in_(document_ids),
                vector.op("@@")(tsquery),
            )
            .order_by(func.ts_rank(vector, tsquery).desc(), Chunk.ordinal)
            .limit(limit)
        )
        return [_chunk_row(*row) for row in (await self.session.execute(stmt)).all()]
