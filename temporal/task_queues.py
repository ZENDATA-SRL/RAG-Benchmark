from __future__ import annotations

from enum import StrEnum


class TaskQueue(StrEnum):
    """Task queues, one per resource profile.

    In the MVP `PARSING` and `CHUNKING` can be served by the same worker, but the queues
    are kept distinct from the start: splitting them later would change the ids of workflows
    already executed, and a durable id is not something that can be renamed after the fact.
    """

    INGESTION = "ingestion"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    EXPERIMENTS = "experiments"


# The queues a single MVP worker polls. Kept as one list so the worker registration and any
# health check read the same source of truth.
WORKER_TASK_QUEUES: tuple[TaskQueue, ...] = (
    TaskQueue.INGESTION,
    TaskQueue.PARSING,
    TaskQueue.CHUNKING,
    TaskQueue.EMBEDDING,
    TaskQueue.EXPERIMENTS,
)
