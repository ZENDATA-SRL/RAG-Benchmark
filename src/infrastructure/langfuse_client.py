from __future__ import annotations

from langfuse import get_client

_client = None


def get_langfuse_client():
    """
    Return a cached Langfuse client instance.

    `langfuse.get_client()` may create internal HTTP clients; caching ensures we can
    shut down the same instance cleanly during FastAPI shutdown/reload.
    """

    global _client
    if _client is None:
        _client = get_client()
    return _client


def shutdown_langfuse_client() -> None:
    global _client
    if _client is None:
        return
    try:
        _client.shutdown()
    finally:
        _client = None

