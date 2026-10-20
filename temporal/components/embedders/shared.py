from langchain_core.embeddings import Embeddings


def resolve_embedder(key: str, params: dict) -> Embeddings:
    """Return the LangChain embedder for a builtin component key."""
    if key == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=params.get("model_name", "text-embedding-3-small"),
            api_key=params.get("api_key") or None,
        )
    if key == "bedrock":
        from langchain_aws import BedrockEmbeddings

        return BedrockEmbeddings(
            model_id=params.get("model_name", "amazon.titan-embed-image-v1"),
            region_name=params.get("region", "us-east-1"),
            aws_access_key_id=params.get("aws_access_key_id", ""),
            aws_secret_access_key=params.get("aws_secret_access_key", ""),
        )
    raise ValueError(f"Unknown embedder key: {key}")