import os
from collections.abc import Callable

from langchain_core.embeddings import Embeddings


def _openai(params: dict) -> Embeddings:
    from langchain_openai import OpenAIEmbeddings

    # The API key is optional: when omitted, the library reads OPENAI_API_KEY.
    credentials = {}
    api_key = params.get("api_key") or os.getenv("OPENAI_API_KEY")
    if api_key:
        credentials["api_key"] = str(api_key)
    return OpenAIEmbeddings(
        model=params.get("model_name", "text-embedding-3-small"),
        **credentials,
    )


def _bedrock(params: dict) -> Embeddings:
    from langchain_aws import BedrockEmbeddings

    # Explicit credentials are optional: when omitted, boto3 falls back to its
    # default chain (AWS_* env vars, then the worker's service role).
    credentials = {
        name: params[name]
        for name in (
            "aws_access_key_id",
            "aws_secret_access_key",
            "aws_session_token",
        )
        if params.get(name)
    }
    return BedrockEmbeddings(
        model_id=params.get("model_name", "amazon.titan-embed-image-v1"),
        region_name=params.get("region")
        or os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or "us-east-1",
        **credentials,
    )


# Factories and not instances: an embedder is bound to the params of one profile, so it
# can only be built when the profile is known.
BUILTIN_EMBEDDERS: dict[str, Callable[[dict], Embeddings]] = {
    "openai": _openai,
    "bedrock": _bedrock,
}


def resolve_embedder(key: str, params: dict) -> Embeddings:
    """Return the LangChain embedder for a builtin component key.

    Raises:
        ValueError: If the key has no implementation.
    """
    factory = BUILTIN_EMBEDDERS.get(key)
    if factory is None:
        raise ValueError(f"Unknown embedder key: {key}")
    return factory(params)
