from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    wrap_model_call,
)
from langchain_aws.middleware import BedrockPromptCachingMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError

# How a run of the agent ended, before the unit looks at what it saved.
STOPPED = "stopped"
MAX_STEPS = "max_steps"


def prompt_caching(cache_key: str) -> list[AgentMiddleware]:
    """The middleware that lets the provider reuse the prefix every model call repeats.

    Each call of a run resends the system prompt, the tools, the task and every step so
    far, and only the last step is new: caching that prefix cuts the cost and the latency
    of the calls after the first.

    OpenAI caches long prefixes on its own; the key routes the calls of one run to the
    same cache. Bedrock caches only where the request marks it, which the `langchain-aws`
    middleware does for the models that support it (Claude, Nova) and skips for the
    others. Either middleware leaves the models of the other provider untouched.
    """

    @wrap_model_call
    async def openai_cache_key(
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        if isinstance(request.model, ChatOpenAI):
            settings = {**request.model_settings, "prompt_cache_key": cache_key}
            request = request.override(model_settings=settings)
        return await handler(request)

    return [
        openai_cache_key,
        BedrockPromptCachingMiddleware(unsupported_model_behavior="ignore"),
    ]


async def run_agent(
    model: BaseChatModel,
    tools: list[BaseTool],
    *,
    system_prompt: str,
    task: str,
    max_steps: int,
    cache_key: str,
    callbacks: list[Any] | None = None,
) -> str:
    """Let the agent work on a task with its tools, for at most `max_steps` model calls.

    No structured final answer is requested: what the agent produces goes through its
    tools, and ending is a tool call too. That keeps the model free to pick a tool on every
    turn, which some providers require (they refuse a forced tool choice).

    A model call and the tools it asks for are two steps of the graph, hence the limit.
    Reaching it is an ordinary end, not an error: what was saved stays saved.

    `cache_key` groups the calls whose prompt prefix the provider may reuse.

    Raises:
        Exception: Whatever the model or a tool raised; the caller sorts provider
            failures from answers the model got wrong.
    """
    agent = create_agent(
        model,
        tools,
        system_prompt=system_prompt,
        middleware=prompt_caching(cache_key),
    )
    try:
        await agent.ainvoke(
            {"messages": [HumanMessage(task)]},
            config={"recursion_limit": 2 * max_steps + 1, "callbacks": callbacks or []},
        )
    except GraphRecursionError:
        return MAX_STEPS
    return STOPPED
