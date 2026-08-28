from __future__ import annotations

from src.settings import Settings, get_settings
from temporalio.client import Client

from temporal.config import worker_data_converter


async def connect(settings: Settings | None = None) -> Client:
    """Connect to the Temporal frontend using the application settings.

    Shares `worker_data_converter` with the worker so a payload written by a client and one
    written by an activity are encoded the same way, size guard included.
    """
    settings = settings or get_settings()
    return await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
        data_converter=worker_data_converter(),
    )
