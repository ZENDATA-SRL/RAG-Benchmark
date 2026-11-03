from __future__ import annotations

from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from src.generation.agent import prompt_caching
from tests.generation_factory import ScriptedAgentModel


async def _settings(model) -> dict:
    """The model settings the call reaches the model with, through the middleware."""
    request = ModelRequest(
        model=model,
        messages=[],
        system_message=None,
        tool_choice=None,
        tools=[],
        response_format=None,
        state={"messages": []},
        runtime=None,
    )
    seen = {}

    async def handler(request: ModelRequest) -> ModelResponse:
        seen.update(request.model_settings)
        return ModelResponse(result=[AIMessage("")])

    async def chain(index: int, request: ModelRequest) -> ModelResponse:
        if index == len(middleware):
            return await handler(request)
        return await middleware[index].awrap_model_call(
            request, lambda next_request: chain(index + 1, next_request)
        )

    middleware = prompt_caching("unit-1")
    await chain(0, request)
    return seen


async def test_openai_calls_of_a_run_share_a_cache_key():
    model = ChatOpenAI(model="gpt-test", api_key="test")

    assert await _settings(model) == {"prompt_cache_key": "unit-1"}


async def test_bedrock_claude_marks_the_prefix_to_cache():
    model = ChatBedrockConverse(
        model="us.anthropic.claude-sonnet-5-5", region_name="eu-west-1"
    )

    settings = await _settings(model)

    assert "prompt_cache_key" not in settings
    assert settings["cache_control"]["type"] == "ephemeral"


async def test_other_models_are_left_untouched():
    bedrock = ChatBedrockConverse(model="meta.llama3-70b", region_name="eu-west-1")

    assert await _settings(bedrock) == {}
    assert await _settings(ScriptedAgentModel(steps=[], seen=[])) == {}
