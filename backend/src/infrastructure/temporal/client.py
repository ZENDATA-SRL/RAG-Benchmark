from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import Any, Protocol, runtime_checkable

from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from src.infrastructure.temporal.codec import data_converter
from src.settings import Settings

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class StartedWorkflow:
    """Outcome of starting a workflow, and whether this call is what started it.

    `started` is false when the deterministic id was already running: a double click on the
    launch button is not a user error, so the caller reports the existing run instead of an
    error, and the flag is what lets it say so honestly.
    """

    workflow_id: str
    started: bool


@runtime_checkable
class WorkflowClient(Protocol):
    """The slice of Temporal the API uses: start a run, cancel it, ask if it is alive.

    Narrow on purpose. The API only ever launches and cancels; the authoritative state of a
    run lives in Temporal but is read from the denormalised `materialization_runs` row, so
    nothing here needs to query history.
    """

    async def start(
        self, workflow: str, *, arg: Any, workflow_id: str, task_queue: str
    ) -> StartedWorkflow:
        """Start a workflow, treating a duplicate id as success rather than an error."""
        ...

    async def cancel(self, workflow_id: str) -> bool:
        """Request cancellation of a running workflow; false if it is not running."""
        ...


class TemporalWorkflowClient(WorkflowClient):
    """`WorkflowClient` backed by a real Temporal connection."""

    def __init__(self, client: Client) -> None:
        self._client = client

    async def start(
        self, workflow: str, *, arg: Any, workflow_id: str, task_queue: str
    ) -> StartedWorkflow:
        """Start a workflow, reporting an already-running id as `started=False`.

        Idempotency is delegated to Temporal: the id is deterministic, so the
        server itself rejects the duplicate and this method turns that rejection into a
        normal outcome.
        """
        try:
            await self._client.start_workflow(
                workflow, arg, id=workflow_id, task_queue=task_queue
            )
        except WorkflowAlreadyStartedError:
            logger.info("workflow %s already started, reusing it", workflow_id)
            return StartedWorkflow(workflow_id=workflow_id, started=False)
        return StartedWorkflow(workflow_id=workflow_id, started=True)

    async def cancel(self, workflow_id: str) -> bool:
        """Request cancellation, returning false if Temporal has no such open run."""
        handle = self._client.get_workflow_handle(workflow_id)
        try:
            await handle.cancel()
        except RPCError as error:
            if error.status in (
                RPCStatusCode.NOT_FOUND,
                RPCStatusCode.FAILED_PRECONDITION,
            ):
                return False
            raise
        return True


async def connect(settings: Settings) -> Client:
    """Connect to the Temporal frontend using the application settings.

    Shares the data converter with the worker so a payload written by the API and one
    written by an activity are encoded the same way, size guard included.
    """
    return await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
        data_converter=data_converter(),
    )


_lock = asyncio.Lock()
_client: TemporalWorkflowClient | None = None


async def get_workflow_client(settings: Settings) -> TemporalWorkflowClient:
    """Return the process-wide workflow client, connecting on first use.

    Lazy and cached: a connection per request would add a handshake to every launch, while
    connecting at import time would make Temporal a hard requirement for serving any
    endpoint at all — including the ones that never touch it.
    """
    global _client
    async with _lock:
        if _client is None:
            _client = TemporalWorkflowClient(await connect(settings))
        return _client


async def reset_workflow_client() -> None:
    """Drop the cached client, so the next use reconnects."""
    global _client
    async with _lock:
        _client = None
