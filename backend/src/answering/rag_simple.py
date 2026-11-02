from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.answering.chat_models import (
    is_output_error,
    missing_credentials,
    resolve_chat_model,
)
from src.answering.contracts import AnswerResult, Retrieve
from src.answering.exceptions import (
    AnswerOutputError,
    AnswerProviderError,
    AnswerSystemUnavailableError,
)
from src.components.builtin.answer_systems.rag_simple import KEY
from src.retrieval.service import RetrievedHit

__all__ = ["KEY", "RagSimple"]


class RagAnswer(BaseModel):
    """The shape the model must answer in."""

    answer: str = Field(description="The answer to the question, or why there is none.")
    refused: bool = Field(
        description=(
            "True when the passages do not contain the answer and none is given."
        )
    )
    cited_sources: list[int] = Field(
        default_factory=list,
        description="Numbers of the passages the answer is based on, e.g. [1, 3].",
    )


class RagSimple:
    """The simplest RAG chain: one search, every hit in the prompt, one answer.

    The question is searched as it is, with the variant's retrieval profile, and all the
    hits it returns go in the prompt as numbered passages: how many is decided by the
    profile's top-k, so what was retrieved and what the model read are the same chunks.
    The model answers in a structured shape that says whether it refused and which
    passages it used, translated back to chunk ids.
    """

    def __init__(
        self, chat_model: Callable[[dict[str, Any]], Any] = resolve_chat_model
    ) -> None:
        self.chat_model = chat_model

    async def answer(
        self, question: str, config: dict[str, Any], retrieve: Retrieve
    ) -> AnswerResult:
        """Search, prompt the model with every hit and translate its citations.

        Raises:
            AnswerSystemUnavailableError: If the provider has no credentials here.
            AnswerOutputError: If the answer is not in the expected shape, or cites a
                passage that was not in the prompt.
            AnswerProviderError: If the model provider failed.
            RetrievalBackendError: If the search failed.
        """
        provider = config["provider"]
        reason = missing_credentials(provider)
        if reason is not None:
            raise AnswerSystemUnavailableError(f"{provider}: {reason}")

        started = time.perf_counter()
        retrieval = await retrieve(question)
        model_started = time.perf_counter()
        messages = [
            SystemMessage(config["system_prompt"]),
            HumanMessage(_prompt(question, retrieval.hits)),
        ]
        runnable = self.chat_model(config).with_structured_output(
            RagAnswer, include_raw=True
        )
        try:
            output = await runnable.ainvoke(messages)
        except Exception as error:
            if is_output_error(error):
                raise AnswerOutputError(str(error) or type(error).__name__) from error
            raise AnswerProviderError(
                provider, str(error) or type(error).__name__
            ) from error
        finished = time.perf_counter()

        parsed = output.get("parsed")
        if output.get("parsing_error") is not None or not isinstance(parsed, RagAnswer):
            raise AnswerOutputError(str(output.get("parsing_error") or "no answer"))
        return AnswerResult(
            answer=parsed.answer,
            refused=parsed.refused,
            citations=_cited_chunks(parsed.cited_sources, retrieval.hits),
            usage=_usage(output.get("raw"), config["model"]),
            timings={
                "retrieval_ms": _ms(started, model_started),
                "model_ms": _ms(model_started, finished),
                "total_ms": _ms(started, finished),
                "retrieval": {
                    "embed_ms": retrieval.timings.embed_ms,
                    "search_ms": retrieval.timings.search_ms,
                    "enrich_ms": retrieval.timings.enrich_ms,
                    "total_ms": retrieval.timings.total_ms,
                },
            },
        )


def _prompt(question: str, hits: list[RetrievedHit]) -> str:
    passages = "\n\n".join(
        f"[{index}] ({hit.filename or 'unknown'}"
        f"{f', page {hit.page}' if hit.page is not None else ''})\n{hit.text or ''}"
        for index, hit in enumerate(hits, start=1)
    )
    return f"Passages:\n\n{passages or '(none)'}\n\nQuestion: {question}"


def _cited_chunks(sources: list[int], hits: list[RetrievedHit]) -> list[uuid.UUID]:
    """The chunk of each cited passage, once each, in the order the model gave.

    A number outside the passages fails the answer: dropping it silently would make the
    attribution look more precise than it was. A passage whose chunk no longer exists has
    no id to record and is left out.
    """
    cited: list[uuid.UUID] = []
    for source in sources:
        if not 1 <= source <= len(hits):
            raise AnswerOutputError(
                f"cited passage {source} but only {len(hits)} were given"
            )
        chunk_id = hits[source - 1].chunk_id
        if chunk_id is not None and chunk_id not in cited:
            cited.append(chunk_id)
    return cited


def _usage(raw: Any, configured_model: str) -> dict[str, Any]:
    """Tokens and the model the provider says it ran, which may differ from the profile's."""
    metadata = getattr(raw, "usage_metadata", None) or {}
    response = getattr(raw, "response_metadata", None) or {}
    usage: dict[str, Any] = {
        "model": response.get("model_name")
        or response.get("model_id")
        or configured_model,
    }
    if "input_tokens" in metadata:
        usage["input_tokens"] = metadata["input_tokens"]
    if "output_tokens" in metadata:
        usage["output_tokens"] = metadata["output_tokens"]
    return usage


def _ms(start: float, end: float) -> float:
    return round((end - start) * 1000, 2)
