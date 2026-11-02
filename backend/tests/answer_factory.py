from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage
from sqlalchemy.ext.asyncio import AsyncSession
from src.answering.rag_simple import RagAnswer
from src.components.builtin.answer_systems import rag_simple
from src.components.models import ComponentVersion
from src.components.registry_seed import seed_builtin_components
from src.components.repository import ComponentRepository, ComponentVersionRepository
from src.infrastructure.database.enums import ComponentType

ANSWER_PROFILES = "/api/v1/answer-profiles"


def rag_params(**overrides: Any) -> dict[str, Any]:
    """Parameters of a `rag_simple` profile, with the ones a test cares about changed."""
    return {
        "provider": "openai",
        "model": "gpt-test",
        "system_prompt": "Answer from the passages only.",
        **overrides,
    }


async def rag_simple_version(session: AsyncSession) -> ComponentVersion:
    """Seed the registry and return the `rag_simple` version."""
    await seed_builtin_components(session)
    component = await ComponentRepository(session).get_by_type_and_key(
        ComponentType.ANSWER_SYSTEM, rag_simple.KEY
    )
    return await ComponentVersionRepository(
        session
    ).get_version_by_component_and_version(component.id, rag_simple.VERSION)


async def answer_profile(client, session, **overrides: Any) -> dict:
    """Create a `rag_simple` profile over the API and return it."""
    version = await rag_simple_version(session)
    response = await client.post(
        ANSWER_PROFILES,
        json={
            "component_version_id": str(version.id),
            "params": rag_params(**overrides),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["profile"]


class ScriptedChatModel:
    """A chat model with structured output that answers by script, without the network.

    `reply` receives the question and returns the answer, or an exception to report as
    an answer that could not be parsed.
    """

    def __init__(self, reply: Callable[[str], RagAnswer | Exception]) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def with_structured_output(self, schema, *, include_raw: bool):
        return self

    async def ainvoke(self, messages):
        prompt = messages[-1].content
        self.prompts.append(prompt)
        parsed = self.reply(prompt.rsplit("Question: ", 1)[-1])
        raw = AIMessage(
            content="",
            usage_metadata={
                "input_tokens": 100,
                "output_tokens": 10,
                "total_tokens": 110,
            },
            response_metadata={"model_name": "gpt-test"},
        )
        if isinstance(parsed, Exception):
            return {"raw": raw, "parsed": None, "parsing_error": parsed}
        return {"raw": raw, "parsed": parsed, "parsing_error": None}
