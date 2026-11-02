from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from src.retrieval.service import RetrievalResult

# The search an answer system is given: a query in, the hits of the variant's index and
# retrieval profile out. Every call is recorded against the execution by whoever binds it.
Retrieve = Callable[[str], Awaitable[RetrievalResult]]


@dataclasses.dataclass(frozen=True)
class AnswerResult:
    """What an answer system returns for one question.

    The same fields an external system returns over HTTP, so a builtin and a remote system
    are recorded and scored by the same code.
    """

    answer: str
    refused: bool
    citations: list[uuid.UUID]
    usage: dict[str, Any]
    timings: dict[str, Any]
    error: str | None = None


class AnswerSystem(Protocol):
    """An implementation that answers a question with the search it is given."""

    async def answer(
        self, question: str, config: dict[str, Any], retrieve: Retrieve
    ) -> AnswerResult:
        """Answer one question.

        Args:
            question: Text of the question.
            config: Parameters of the answer profile.
            retrieve: Search bound to the variant and the execution.

        Raises:
            AnswerOutputError: If the model answered in an unexpected shape.
            AnswerProviderError: If the model provider failed.
            RetrievalBackendError: If the search failed.
        """
        ...
