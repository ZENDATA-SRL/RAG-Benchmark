from __future__ import annotations

from src.infrastructure.temporal import connect as _connect
from src.settings import Settings, get_settings
from temporalio.client import Client


async def connect(settings: Settings | None = None) -> Client:
    """Connect to the Temporal frontend using the application settings.

    Shares the data converter with the API so a payload written by a client and one written
    by an activity are encoded the same way, size guard included.
    """
    return await _connect(settings or get_settings())
