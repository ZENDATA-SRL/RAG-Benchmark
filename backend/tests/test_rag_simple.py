from __future__ import annotations

import uuid

import pytest
from langchain_core.messages import AIMessage
from src.answering.exceptions import (
    AnswerOutputError,
    AnswerProviderError,
    AnswerSystemUnavailableError,
)
from src.answering.rag_simple import RagAnswer, RagSimple
from src.infrastructure.observability import LangfuseTracer
from src.retrieval.service import RetrievalResult, RetrievalTimings, RetrievedHit
from tests.tracing_factory import FakeLangfuse

CONFIG = {
    "provider": "openai",
    "model": "gpt-test",
    "system_prompt": "Answer from the passages only.",
    "temperature": 0,
    "max_tokens": 256,
}
CHUNKS = [uuid.uuid4() for _ in range(3)]


class FakeChatModel:
    """Stands in for a LangChain chat model with structured output, without the network."""

    def __init__(self, parsed=None, *, error: Exception | None = None, raw=None):
        self.parsed = parsed
        self.error = error
        self.raw = raw or AIMessage(
            content="",
            usage_metadata={
                "input_tokens": 300,
                "output_tokens": 20,
                "total_tokens": 320,
            },
            response_metadata={"model_name": "gpt-test-2026"},
        )
        self.messages = None

    def with_structured_output(self, schema, *, include_raw: bool):
        assert schema is RagAnswer and include_raw
        return self

    async def ainvoke(self, messages):
        self.messages = messages
        if self.error is not None:
            raise self.error
        if isinstance(self.parsed, Exception):
            return {"raw": self.raw, "parsed": None, "parsing_error": self.parsed}
        return {"raw": self.raw, "parsed": self.parsed, "parsing_error": None}


class Searches:
    """The retrieve function an answer system receives: records the queries it gets."""

    def __init__(self, chunk_ids=CHUNKS) -> None:
        self.queries: list[str] = []
        self.chunk_ids = chunk_ids

    async def __call__(self, query: str) -> RetrievalResult:
        self.queries.append(query)
        return RetrievalResult(
            index_build_id=uuid.uuid4(),
            retrieval_profile_id=uuid.uuid4(),
            corpus_id=None,
            chunking_configuration_id=uuid.uuid4(),
            hits=[
                RetrievedHit(
                    rank=rank,
                    score=1.0 / rank,
                    stage="final",
                    chunk_id=chunk_id,
                    document_id=uuid.uuid4(),
                    filename="doc.pdf",
                    ordinal=rank,
                    page=rank,
                    text=f"passage text {rank}",
                )
                for rank, chunk_id in enumerate(self.chunk_ids, start=1)
            ],
            timings=RetrievalTimings(
                embed_ms=1.0, search_ms=2.0, enrich_ms=0.5, total_ms=3.5
            ),
        )


@pytest.fixture(autouse=True)
def openai_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


async def _answer(model: FakeChatModel, searches: Searches | None = None):
    return await RagSimple(lambda params: model).answer(
        "What is it?", CONFIG, searches or Searches()
    )


async def test_an_answer_cites_chunks_by_id_and_reports_its_usage() -> None:
    model = FakeChatModel(
        RagAnswer(answer="It is X.", refused=False, cited_sources=[3, 1, 3])
    )
    searches = Searches()

    result = await _answer(model, searches)

    assert searches.queries == ["What is it?"]
    assert (result.answer, result.refused) == ("It is X.", False)
    # Translated to chunk ids, once each, in the order the model gave.
    assert result.citations == [CHUNKS[2], CHUNKS[0]]
    assert result.usage == {
        "model": "gpt-test-2026",
        "input_tokens": 300,
        "output_tokens": 20,
    }
    assert set(result.timings) == {"retrieval_ms", "model_ms", "total_ms", "retrieval"}
    assert result.timings["retrieval"]["total_ms"] == 3.5
    # Every hit is in the prompt as a numbered passage, after the system prompt.
    system, human = model.messages
    assert system.content == CONFIG["system_prompt"]
    assert "[1] (doc.pdf, page 1)\npassage text 1" in human.content
    assert "[3] (doc.pdf, page 3)" in human.content
    assert human.content.endswith("Question: What is it?")


async def test_a_refusal_is_recorded_with_no_citation() -> None:
    model = FakeChatModel(RagAnswer(answer="Not in the passages.", refused=True))

    result = await _answer(model)

    assert result.refused is True
    assert result.citations == []


async def test_an_answer_not_in_the_expected_shape_is_an_output_error() -> None:
    model = FakeChatModel(ValueError("missing field refused"))

    with pytest.raises(AnswerOutputError):
        await _answer(model)


async def test_a_citation_outside_the_passages_is_an_output_error() -> None:
    model = FakeChatModel(RagAnswer(answer="X", refused=False, cited_sources=[4]))

    with pytest.raises(AnswerOutputError, match="only 3 were given"):
        await _answer(model)


async def test_a_failure_of_the_provider_is_transient() -> None:
    model = FakeChatModel(error=ConnectionError("rate limited"))

    with pytest.raises(AnswerProviderError):
        await _answer(model)


async def test_a_provider_without_credentials_fails_before_searching(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY")
    searches = Searches()

    with pytest.raises(AnswerSystemUnavailableError, match="OPENAI_API_KEY"):
        await _answer(FakeChatModel(RagAnswer(answer="X", refused=False)), searches)
    assert searches.queries == []


async def test_a_cited_chunk_that_no_longer_exists_is_left_out() -> None:
    model = FakeChatModel(RagAnswer(answer="X", refused=False, cited_sources=[1, 2]))

    result = await _answer(model, Searches([None, CHUNKS[1]]))

    assert result.citations == [CHUNKS[1]]


async def test_the_call_to_the_model_is_traced_as_a_generation() -> None:
    client = FakeLangfuse()
    model = FakeChatModel(
        RagAnswer(answer="It is X.", refused=False, cited_sources=[1])
    )

    await RagSimple(lambda params: model).answer(
        "What is it?", CONFIG, Searches(), LangfuseTracer(client)
    )

    (generation,) = client.observations
    assert (generation.name, generation.as_type) == ("model", "generation")
    assert generation.fields["model"] == "gpt-test"
    assert generation.fields["model_parameters"] == {
        "temperature": 0,
        "max_tokens": 256,
    }
    assert [message["role"] for message in generation.fields["input"]] == [
        "system",
        "user",
    ]
    assert generation.updated("output") == {
        "answer": "It is X.",
        "refused": False,
        "cited_sources": [1],
    }
    # The model the provider ran, which may differ from the configured one.
    assert generation.updated("model") == "gpt-test-2026"
    assert generation.updated("usage_details") == {"input": 300, "output": 20}


async def test_a_failed_call_to_the_model_marks_its_generation() -> None:
    client = FakeLangfuse()
    model = FakeChatModel(error=ConnectionError("rate limited"))

    with pytest.raises(AnswerProviderError):
        await RagSimple(lambda params: model).answer(
            "What is it?", CONFIG, Searches(), LangfuseTracer(client)
        )

    (generation,) = client.observations
    assert generation.updated("level") == "ERROR"
