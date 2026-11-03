from __future__ import annotations

import asyncio
import dataclasses
import datetime as dt
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.generation.models import (
    GeneratedQuestion,
    GeneratedQuestionChunk,
    GenerationJob,
    GenerationUnit,
)
from src.generation.refs import Refs
from src.generation.repository import (
    CorpusTextRepository,
    ProposalRepository,
)
from src.generation.verification import Citation, CitedChunk, verify
from src.generation.zones import zone_of
from src.infrastructure.database.enums import GenerationPhase
from src.infrastructure.observability import NULL_TRACER, Tracer
from src.transfers.matching import normalize

# Every answer of a tool stays in the agent's context for the rest of the unit, so each is
# cut to a size that is useful once and cheap to carry.
MAX_WINDOW_CHARS = 6000
OUTLINE_PAGE = 20
CATALOGUE_PAGE = 20
SEARCH_RESULTS = 5
FIND_RESULTS = 5
MAX_NEIGHBOURS = 3
_EXCERPT_CHARS = 160

SAVED = "saved"
DISCARDED = "discarded"
TARGET_REACHED = "target_reached"


@dataclasses.dataclass
class UnitScope:
    """What one unit may read and where its questions go, shared by all its tools.

    `documents` are the documents the tools see: the unit's own in the document phase,
    all those of the job in the cross phase. `existing` holds the questions a new one must
    not repeat, and grows with every question saved.
    """

    session: AsyncSession
    job: GenerationJob
    unit: GenerationUnit
    refs: Refs
    documents: list[uuid.UUID]
    existing: list[str]
    target: int
    zones: list[range] = dataclasses.field(default_factory=list)
    summaries: dict[uuid.UUID, tuple[str | None, list[str]]] = dataclasses.field(
        default_factory=dict
    )
    tracer: Tracer = NULL_TRACER
    on_step: Callable[[], None] = lambda: None
    saved: int = 0
    finished: bool = False

    @property
    def configuration_id(self) -> uuid.UUID:
        return self.job.chunking_configuration_id

    @property
    def remaining(self) -> int:
        return max(0, self.target - self.saved)


class _Citation(BaseModel):
    chunk: str = Field(description="Reference of the chunk, e.g. d1:c12.")
    quote: str = Field(
        description="A passage copied exactly from that chunk that supports the answer."
    )


class _ListDocuments(BaseModel):
    offset: int = Field(default=0, ge=0, description="Where the page starts.")


class _ReadDocument(BaseModel):
    doc: str = Field(description="Reference of the document, e.g. d1.")
    offset: int = Field(default=0, ge=0, description="Character to start from.")
    max_chars: int = Field(default=MAX_WINDOW_CHARS, ge=200, le=MAX_WINDOW_CHARS)


class _Outline(BaseModel):
    doc: str = Field(description="Reference of the document, e.g. d1.")
    offset: int = Field(default=0, ge=0, description="Chunk to start from.")


class _FindChunks(BaseModel):
    doc: str = Field(description="Reference of the document, e.g. d1.")
    passage: str = Field(
        description="A passage of the document, copied as you read it."
    )


class _ReadChunk(BaseModel):
    chunk: str = Field(description="Reference of the chunk, e.g. d1:c12.")


class _Neighbours(BaseModel):
    chunk: str = Field(description="Reference of the chunk, e.g. d1:c12.")
    n: int = Field(
        default=1, ge=1, le=MAX_NEIGHBOURS, description="Chunks on each side."
    )


class _Search(BaseModel):
    query: str = Field(description="What to look for, in your own words.")
    docs: list[str] | None = Field(
        default=None,
        description="Documents to search, e.g. ['d1', 'd3']; all if absent.",
    )


class _Submit(BaseModel):
    question: str = Field(description="The question, as a person would ask it.")
    answer: str = Field(description="The expected answer, from the cited chunks only.")
    citations: list[_Citation] = Field(
        description="The chunks that hold the answer, each with a quote from it."
    )


class _Finish(BaseModel):
    summary: str = Field(
        default="", description="Two or three sentences on what the document is about."
    )
    topics: list[str] = Field(
        default_factory=list, description="The main topics of the document."
    )


def _excerpt(text: str, size: int = _EXCERPT_CHARS) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= size else flat[: size - 1] + "…"


def _page(page: int | None) -> str:
    return f" p.{page}" if page is not None else ""


class GenerationTools:
    """The tools of one unit: reads limited to its documents, and the submission.

    The reads come from the database, bound to the job's chunking configuration and to
    the unit's documents: a reference to anything else is answered as unknown. Every call
    reports a step, which the worker turns into a heartbeat.
    """

    def __init__(self, scope: UnitScope) -> None:
        self.scope = scope
        self.texts = CorpusTextRepository(scope.session)
        self.proposals = ProposalRepository(scope.session)
        # The agent runs the calls of one turn concurrently, but they share one session,
        # which takes one statement at a time; in turn order a submission also sees the
        # ones before it when looking for duplicates.
        self._lock = asyncio.Lock()

    def tools(self) -> list[BaseTool]:
        """The tools as the agent is given them."""
        specs: list[tuple[str, str, type[BaseModel], Callable[..., Awaitable[str]]]] = [
            (
                "list_documents",
                (
                    "List the documents you can read: reference, file name, length of "
                    "the text, number of chunks and a summary when there is one."
                ),
                _ListDocuments,
                self.list_documents,
            ),
            (
                "read_document",
                "Read a window of the text of a document, from a character offset.",
                _ReadDocument,
                self.read_document,
            ),
            (
                "document_outline",
                "List the chunks of a document: reference, page, zone and first words.",
                _Outline,
                self.document_outline,
            ),
            (
                "find_chunks",
                "Find which chunks of a document contain a passage you read.",
                _FindChunks,
                self.find_chunks,
            ),
            (
                "read_chunk",
                "Read the whole text of a chunk.",
                _ReadChunk,
                self.read_chunk,
            ),
            (
                "neighbours",
                "Read a chunk with the chunks before and after it.",
                _Neighbours,
                self.neighbours,
            ),
            (
                "search",
                (
                    "Search the chunks most relevant to a query, in your documents or in "
                    "the ones given."
                ),
                _Search,
                self.search,
            ),
            (
                "submit_question",
                (
                    "Submit one question with its answer and the chunks that hold it. "
                    "Answers whether it was saved or why it was discarded."
                ),
                _Submit,
                self.submit_question,
            ),
        ]
        tools: list[BaseTool] = [
            StructuredTool.from_function(
                coroutine=self._stepped(function),
                name=name,
                description=description,
                args_schema=schema,
            )
            for name, description, schema, function in specs
        ]
        tools.append(
            StructuredTool.from_function(
                coroutine=self._stepped(self.finish),
                name="finish",
                description="End this run: when the target is reached or nothing more "
                "is worth asking.",
                args_schema=_Finish,
                # The run ends on this call, without asking the model again.
                return_direct=True,
            )
        )
        return tools

    def _stepped(
        self, function: Callable[..., Awaitable[str]]
    ) -> Callable[..., Awaitable[str]]:
        async def call(**kwargs: Any) -> str:
            async with self._lock:
                self.scope.on_step()
                return await function(**kwargs)

        return call

    def _document(self, ref: str) -> uuid.UUID | None:
        document_id = self.scope.refs.resolve_document(ref)
        return document_id if document_id in self.scope.documents else None

    async def _chunk(self, ref: str):
        position = self.scope.refs.resolve_chunk(ref)
        if position is None or position[0] not in self.scope.documents:
            return None
        found = await self.texts.chunks_at(self.scope.configuration_id, [position])
        return found.get(position)

    def _row(self, chunk) -> str:
        zone = ""
        if self.scope.zones and chunk.document_id == self.scope.unit.document_id:
            index = zone_of(chunk.ordinal, self.scope.zones)
            zone = f" zone {index}" if index is not None else ""
        return (
            f"{self.scope.refs.chunk(chunk.document_id, chunk.ordinal)}"
            f"{_page(chunk.page)}{zone}"
        )

    async def list_documents(self, offset: int = 0) -> str:
        ids = self.scope.documents[offset : offset + CATALOGUE_PAGE]
        catalogue = await self.texts.catalogue(self.scope.configuration_id, ids)
        lines = []
        for document_id in ids:
            row = catalogue.get(document_id)
            if row is None:
                continue
            summary, topics = self.scope.summaries.get(document_id, (None, []))
            about = summary or f"opens with: {_excerpt(row.head)}"
            lines.append(
                f"{self.scope.refs.document(document_id)} | {row.filename} | path: | "
                f"{row.text_length} chars | {row.chunk_count} chunks | {about}"
                + (f" | topics: {', '.join(topics)}" if topics else "")
            )
        end = offset + len(ids)
        more = f"\n(more from offset {end})" if end < len(self.scope.documents) else ""
        return ("\n".join(lines) or "no documents") + more

    async def read_document(
        self, doc: str, offset: int = 0, max_chars: int = MAX_WINDOW_CHARS
    ) -> str:
        document_id = self._document(doc)
        if document_id is None:
            return f"unknown document {doc}"
        window, total = await self.texts.text_window(
            self.scope.configuration_id,
            document_id,
            offset=offset,
            length=min(max_chars, MAX_WINDOW_CHARS),
        )
        end = offset + len(window)
        tail = f"next offset: {end}" if end < total else "end of the document"
        return f"[{doc} characters {offset}-{end} of {total}]\n{window}\n[{tail}]"

    async def document_outline(self, doc: str, offset: int = 0) -> str:
        document_id = self._document(doc)
        if document_id is None:
            return f"unknown document {doc}"
        rows = await self.texts.outline(
            self.scope.configuration_id,
            document_id,
            offset=offset,
            limit=OUTLINE_PAGE + 1,
        )
        lines = []
        for ordinal, page, text in rows[:OUTLINE_PAGE]:
            zone = ""
            if self.scope.zones and document_id == self.scope.unit.document_id:
                index = zone_of(ordinal, self.scope.zones)
                zone = f" zone {index}" if index is not None else ""
            lines.append(
                f"{self.scope.refs.chunk(document_id, ordinal)}{_page(page)}{zone}: "
                f"{_excerpt(text, 120)}"
            )
        more = (
            f"\n(more from offset {offset + OUTLINE_PAGE})"
            if len(rows) > OUTLINE_PAGE
            else ""
        )
        return ("\n".join(lines) or "no chunks at this offset") + more

    async def find_chunks(self, doc: str, passage: str) -> str:
        document_id = self._document(doc)
        if document_id is None:
            return f"unknown document {doc}"
        wanted = normalize(passage)
        if not wanted:
            return "give a passage to look for"
        chunks = await self.texts.document_chunks(
            self.scope.configuration_id, document_id
        )
        found = [chunk for chunk in chunks if wanted in normalize(chunk.text)]
        if not found:
            return (
                "no chunk contains this passage as a whole: it may span two chunks; "
                "try a shorter part of it"
            )
        return "\n".join(
            f"{self._row(chunk)}: {_excerpt(chunk.text)}"
            for chunk in found[:FIND_RESULTS]
        )

    async def read_chunk(self, chunk: str) -> str:
        row = await self._chunk(chunk)
        if row is None:
            return f"unknown chunk {chunk}"
        return f"[{self._row(row)} | {row.filename}]\n{row.text}"

    async def neighbours(self, chunk: str, n: int = 1) -> str:
        row = await self._chunk(chunk)
        if row is None:
            return f"unknown chunk {chunk}"
        n = max(1, min(n, MAX_NEIGHBOURS))
        rows = await self.texts.chunk_range(
            self.scope.configuration_id,
            row.document_id,
            first=row.ordinal - n,
            last=row.ordinal + n,
        )
        return "\n\n".join(f"[{self._row(item)}]\n{item.text}" for item in rows)

    async def search(self, query: str, docs: list[str] | None = None) -> str:
        documents = self.scope.documents
        if docs:
            documents = [d for d in (self._document(ref) for ref in docs) if d]
            if not documents:
                return "none of these documents can be searched"
        rows = await self.texts.search(
            self.scope.configuration_id, documents, query, limit=SEARCH_RESULTS
        )
        if not rows:
            return "no chunk matches"
        return "\n".join(
            f"{self._row(row)} | {row.filename}: {_excerpt(row.text)}" for row in rows
        )

    async def submit_question(
        self, question: str, answer: str, citations: list[_Citation | dict]
    ) -> str:
        """Check a question and save it at once, in its own transaction.

        Saved one at a time, so an interrupted unit loses nothing and a resumed one
        knows what it already delivered. A refusal is counted on the unit by reason
        and returned to the agent, which can fix the question and submit it again.
        """
        scope = self.scope
        if scope.remaining == 0:
            return f"{TARGET_REACHED}: no more questions are needed, call finish"
        cited = [
            Citation(ref=item.chunk, quote=item.quote)
            for item in (_Citation.model_validate(raw) for raw in citations)
        ]
        resolved: dict[str, CitedChunk] = {}
        for citation in cited:
            row = await self._chunk(citation.ref)
            if row is not None:
                resolved[citation.ref] = CitedChunk(
                    row.chunk_id, row.document_id, row.text
                )
        verdict = verify(
            question=question,
            answer=answer,
            citations=cited,
            resolved=resolved,
            phase=scope.unit.phase,
            unit_document_id=scope.unit.document_id,
            existing=scope.existing,
            limits=scope.job.params.get("limits", {}),
        )
        with scope.tracer.observe(
            "verify",
            input={
                "question": question,
                "answer": answer,
                "citations": [dataclasses.asdict(c) for c in cited],
            },
        ) as span:
            span.update(
                output={
                    "saved": verdict.accepted,
                    "reason": verdict.reason,
                    "kind": verdict.kind.value if verdict.kind else None,
                }
            )
        if not verdict.accepted:
            discards = dict(scope.unit.discards or {})
            discards[verdict.reason] = discards.get(verdict.reason, 0) + 1
            scope.unit.discards = discards
            await scope.session.commit()
            return f"{DISCARDED}: {verdict.reason}: {verdict.detail}"

        await self.proposals.add(
            GeneratedQuestion(
                generation_job_id=scope.job.id,
                unit_id=scope.unit.id,
                kind=verdict.kind,
                text=question.strip(),
                answer=answer.strip(),
                # Stamped by the application, like questions: `now()` is the start of
                # the transaction, and the queue is ordered by when each was saved.
                created_at=dt.datetime.now(dt.UTC),
            ),
            [
                GeneratedQuestionChunk(
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    relevance=item.relevance,
                    quote=item.quote,
                    rank=rank,
                )
                for rank, item in enumerate(verdict.evidence, start=1)
            ],
        )
        scope.saved += 1
        scope.unit.produced = (scope.unit.produced or 0) + 1
        scope.existing.append(question.strip())
        await scope.session.commit()
        if scope.remaining == 0:
            return (
                f"{SAVED} ({verdict.kind.value}). The target is reached: call finish."
            )
        return f"{SAVED} ({verdict.kind.value}). {scope.remaining} question(s) to go."

    async def finish(self, summary: str = "", topics: list[str] | None = None) -> str:
        scope = self.scope
        scope.finished = True
        if scope.unit.phase is GenerationPhase.DOCUMENT:
            scope.unit.summary = summary.strip() or None
            scope.unit.topics = [
                topic.strip() for topic in topics or [] if topic.strip()
            ]
        return "finished"
