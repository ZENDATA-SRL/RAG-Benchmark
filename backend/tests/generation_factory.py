from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.artifacts.models import Chunk, ChunkResult, ParsingResult
from src.documents.models import Document
from tests.pipeline_factory import Scenario, build_scenario

QA_SETS = "/api/v1/qa-sets"
GENERATION_JOBS = "/api/v1/generation-jobs"
GENERATED_QUESTIONS = "/api/v1/generated-questions"

# Three documents of different length, each chunk a passage of its own.
TEXTS = {
    "ready-0.pdf": [
        "Il presente capitolato disciplina la fornitura di servizi informatici al comune.",
        (
            "La penale per ritardo nella consegna è pari all'1 per mille dell'importo "
            "contrattuale per ogni giorno lavorativo di ritardo."
        ),
        "L'assistenza tecnica è garantita dal lunedì al venerdì dalle nove alle diciotto.",
        "Il contratto ha una durata di tre anni rinnovabile una sola volta.",
    ],
    "ready-1.pdf": [
        "Le fatture sono pagate a sessanta giorni dalla data di ricezione.",
        "Le fatture sono trasmesse esclusivamente in formato elettronico.",
    ],
    "ready-2.pdf": [
        "Il fornitore nomina un referente tecnico entro dieci giorni dalla firma.",
        "Il referente tecnico coordina gli interventi di assistenza sul posto.",
        "Ogni intervento sul posto è registrato in un verbale firmato dal comune.",
    ],
}


@dataclasses.dataclass
class Corpus:
    """A corpus of three documents materialised in one configuration, and a set on it."""

    scenario: Scenario
    qa_set_id: str
    documents: list[Document]
    chunks: dict[str, list[Chunk]]

    @property
    def configuration_id(self) -> str:
        return self.scenario.configuration_id


async def build_corpus(
    session: AsyncSession, client, *, unmaterialised: int = 0
) -> Corpus:
    """Three documents with known chunk texts and parsed text, and an empty QA set."""
    scenario = await build_scenario(
        session, ready=3, missing=unmaterialised, chunks_per_document=4
    )
    chunks: dict[str, list[Chunk]] = {}
    for document in scenario.ready:
        texts = TEXTS[document.filename]
        rows = list(
            (
                await session.scalars(
                    select(Chunk)
                    .join(ChunkResult, ChunkResult.id == Chunk.chunk_result_id)
                    .where(
                        ChunkResult.document_id == document.id,
                        ChunkResult.chunking_configuration_id
                        == scenario.configuration.id,
                    )
                    .order_by(Chunk.ordinal)
                )
            ).all()
        )
        for chunk in rows[len(texts) :]:
            await session.delete(chunk)
        for chunk, text in zip(rows, texts, strict=False):
            chunk.text = text
        result = await session.scalar(
            select(ChunkResult).where(
                ChunkResult.document_id == document.id,
                ChunkResult.chunking_configuration_id == scenario.configuration.id,
            )
        )
        result.chunk_count = len(texts)
        parse = await session.get(ParsingResult, result.parsing_result_id)
        parse.output_text = "\n".join(texts)
        chunks[document.filename] = rows[: len(texts)]
    await session.flush()
    created = await client.post(
        QA_SETS, json={"name": "generated", "origin_corpus_id": scenario.corpus_id}
    )
    assert created.status_code == 201, created.text
    return Corpus(
        scenario=scenario,
        qa_set_id=created.json()["id"],
        documents=list(scenario.ready),
        chunks=chunks,
    )


def tool_call(name: str, **args: Any) -> AIMessage:
    """A model turn that calls one tool."""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": f"call-{uuid.uuid4().hex[:8]}"}],
    )


def submit(question: str, answer: str, *citations: tuple[str, str]) -> AIMessage:
    return tool_call(
        "submit_question",
        question=question,
        answer=answer,
        citations=[{"chunk": chunk, "quote": quote} for chunk, quote in citations],
    )


def last_tool_result(messages: Sequence[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, ToolMessage):
            return str(message.content)
    return ""


Step = AIMessage | Callable[[Sequence[BaseMessage]], AIMessage]


class ScriptedAgentModel(BaseChatModel):
    """A chat model that plays a script of turns, without the network.

    Each step is a message, or a function of the conversation so far for a turn that
    reacts to what a tool answered. Past the end of the script it stops calling tools.
    """

    steps: list[Any]
    seen: list[list[BaseMessage]]
    error: Exception | None = None

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if self.error is not None:
            raise self.error
        self.seen.append(list(messages))
        turn = len(self.seen) - 1
        if turn < len(self.steps):
            step = self.steps[turn]
            message = step(messages) if callable(step) else step
        else:
            message = AIMessage(content="done")
        return ChatResult(generations=[ChatGeneration(message=message)])


def scripted(*steps: Step, error: Exception | None = None) -> Callable[[dict], Any]:
    """A chat model factory returning one scripted model, kept for inspection."""
    model = ScriptedAgentModel(steps=list(steps), seen=[], error=error)

    def factory(params: dict) -> ScriptedAgentModel:
        factory.params = params
        return model

    factory.model = model
    return factory
