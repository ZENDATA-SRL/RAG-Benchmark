from __future__ import annotations

from src.answering import rag_simple
from src.answering.contracts import AnswerSystem

# `builtin` answer systems: the key maps to a class in this repository, run in-process by
# the worker. Keyed like the descriptors, so the worker can check none is missing at boot.
BUILTIN_ANSWER_SYSTEMS: dict[str, AnswerSystem] = {
    rag_simple.KEY: rag_simple.RagSimple(),
}


def resolve_answer_system(key: str) -> AnswerSystem:
    """Return the answer system implementation for a component key.

    Raises:
        KeyError: If the key has no implementation.
    """
    return BUILTIN_ANSWER_SYSTEMS[key]
