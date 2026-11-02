from __future__ import annotations

import os
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel


def missing_credentials(provider: str) -> str | None:
    """Why a provider cannot be called from this process, or `None` if it can.

    Only the presence of credentials is checked, without calling the provider: a key that
    is present but wrong surfaces as a failed execution with the provider's message.
    """
    if provider == "openai":
        return None if os.getenv("OPENAI_API_KEY") else "OPENAI_API_KEY is not set"
    if provider == "bedrock":
        import boto3

        # The same chain the Bedrock client uses: AWS_* variables, then the profile.
        if boto3.Session().get_credentials() is None:
            return "no AWS credentials found"
        return None
    return f"unknown provider {provider!r}"


# Bedrock Claude families that reject a sampling temperature and a forced tool choice:
# the structured answer is then requested with the tool offered as "auto".
_BEDROCK_AUTO_TOOL_FAMILIES = (
    "claude-sonnet-5",
    "claude-opus-5",
    "claude-haiku-5",
    "claude-fable-5",
)


def resolve_chat_model(params: dict[str, Any]) -> BaseChatModel:
    """Build the chat model a profile names, with the credentials of the environment.

    Raises:
        ValueError: If the provider is not supported.
    """
    provider = params["provider"]
    temperature = params.get("temperature", 0)
    max_tokens = params.get("max_tokens", 1024)
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=params["model"],
            temperature=temperature,
            max_tokens=max_tokens,
            # Retries are the workflow's, with backoff: the client must not hide them.
            max_retries=0,
        )
    if provider == "bedrock":
        from langchain_aws import ChatBedrockConverse

        options: dict[str, Any]
        if any(family in params["model"] for family in _BEDROCK_AUTO_TOOL_FAMILIES):
            options = {"temperature": None, "supports_tool_choice_values": ("auto",)}
        else:
            options = {"temperature": temperature}
        return ChatBedrockConverse(
            model=params["model"],
            max_tokens=max_tokens,
            region_name=params.get("region") or None,
            **options,
        )
    raise ValueError(f"Unknown chat model provider: {provider}")


def is_output_error(error: Exception) -> bool:
    """Whether a failure of the call is about the answer and not about the provider.

    A truncated or filtered answer is the model's, and asking again returns the same.
    """
    return type(error).__name__ in {
        "LengthFinishReasonError",
        "ContentFilterFinishReasonError",
        "OutputParserException",
        "ValidationError",
    }
