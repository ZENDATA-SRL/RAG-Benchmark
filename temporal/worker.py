from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from src.answering.availability import sync_answer_system_availability
from src.settings import get_settings
from temporalio.worker import Worker

from temporal.activities import ALL_ACTIVITIES
from temporal.client import connect
from temporal.components import assert_registry_complete
from temporal.config import activity_session, dispose_worker_engine
from temporal.task_queues import WORKER_TASK_QUEUES
from temporal.workflows import ALL_WORKFLOWS

logger = logging.getLogger(__name__)

_GRACEFUL_SHUTDOWN = timedelta(seconds=30)


async def run_worker() -> None:
    """Connect and serve every task queue until interrupted.

    `assert_registry_complete()` runs first: a declared-but-unimplemented builtin must fail
    at boot, not hours into a run when the first activity tries to resolve it. Then the
    answer systems are marked available or not from this process's model credentials,
    which the API cannot see.
    """
    assert_registry_complete()
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    async with activity_session() as session:
        await sync_answer_system_availability(session)

    client = await connect(settings)

    # One worker per task queue. In the MVP a single process serves all of them, but
    # keeping them as distinct workers is what lets a queue be moved to its own worker later
    # without touching the workflow ids already executed.
    workers = [
        Worker(
            client,
            task_queue=queue.value,
            workflows=ALL_WORKFLOWS,
            activities=ALL_ACTIVITIES,
            graceful_shutdown_timeout=_GRACEFUL_SHUTDOWN,
        )
        for queue in WORKER_TASK_QUEUES
    ]

    logger.info(
        "worker polling queues: %s", ", ".join(q.value for q in WORKER_TASK_QUEUES)
    )
    try:
        async with asyncio.TaskGroup() as group:
            for worker in workers:
                group.create_task(worker.run())
    finally:
        await dispose_worker_engine()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
