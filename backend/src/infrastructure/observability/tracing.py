from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Iterator
from typing import Any, Protocol

from langfuse import Langfuse, propagate_attributes

from src.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class Observation(Protocol):
    """A span or generation being recorded; `update` adds what became known."""

    @property
    def id(self) -> str | None: ...

    def update(self, **fields: Any) -> None: ...


class Tracer(Protocol):
    """Where executions are traced. Callers never check whether tracing is configured.

    Every method is best-effort: a failure of the backend is logged and never raised, so
    tracing can not change the outcome of what it observes. An exception of the observed
    code, instead, always goes through.
    """

    enabled: bool

    def trace_id(self, seed: str) -> str | None:
        """The trace id derived from `seed`, or `None` when tracing is off."""
        ...

    def observe(
        self,
        name: str,
        *,
        as_type: str = "span",
        trace_id: str | None = None,
        **fields: Any,
    ) -> contextlib.AbstractContextManager[Observation]:
        """Record the enclosed block as an observation, child of the current one.

        With `trace_id` the observation is the root of that trace. An exception leaving the
        block marks the observation `ERROR` with the message.
        """
        ...

    def attributes(
        self, *, metadata: dict[str, str], tags: list[str], trace_name: str
    ) -> contextlib.AbstractContextManager[None]:
        """Put trace-level metadata and tags on every observation opened in the block."""
        ...

    async def create_dataset(
        self, name: str, *, description: str, metadata: dict[str, Any]
    ) -> str | None:
        """Create (or reuse, by name) a dataset; its id, or `None` if it failed."""
        ...

    async def upsert_dataset_item(
        self,
        dataset_name: str,
        item_id: str,
        *,
        input: Any,
        expected_output: Any,
        metadata: dict[str, Any],
    ) -> bool:
        """Create or replace a dataset item by id; whether it succeeded."""
        ...

    async def link_dataset_run(
        self,
        run_name: str,
        item_id: str,
        *,
        trace_id: str,
        observation_id: str | None,
        metadata: dict[str, Any],
    ) -> None:
        """Record a trace as the outcome of a dataset item in a named dataset run."""
        ...

    async def flush(self) -> None:
        """Send what is buffered, so a stopped process does not lose it."""
        ...

    async def shutdown(self) -> None:
        """Flush and release the exporter."""
        ...

    async def check(self) -> bool:
        """Whether the backend accepts the configured credentials."""
        ...


class _NullObservation:
    id = None

    def update(self, **fields: Any) -> None:
        pass


NULL_OBSERVATION = _NullObservation()


class NullTracer:
    """The tracer used when tracing is off: every call does nothing."""

    enabled = False

    def trace_id(self, seed: str) -> str | None:
        return None

    @contextlib.contextmanager
    def observe(
        self,
        name: str,
        *,
        as_type: str = "span",
        trace_id: str | None = None,
        **fields: Any,
    ) -> Iterator[Observation]:
        yield NULL_OBSERVATION

    @contextlib.contextmanager
    def attributes(
        self, *, metadata: dict[str, str], tags: list[str], trace_name: str
    ) -> Iterator[None]:
        yield None

    async def create_dataset(
        self, name: str, *, description: str, metadata: dict[str, Any]
    ) -> str | None:
        return None

    async def upsert_dataset_item(
        self,
        dataset_name: str,
        item_id: str,
        *,
        input: Any,
        expected_output: Any,
        metadata: dict[str, Any],
    ) -> bool:
        return False

    async def link_dataset_run(
        self,
        run_name: str,
        item_id: str,
        *,
        trace_id: str,
        observation_id: str | None,
        metadata: dict[str, Any],
    ) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def check(self) -> bool:
        return False


NULL_TRACER = NullTracer()


class _LangfuseObservation:
    def __init__(self, observation: Any) -> None:
        self._observation = observation

    @property
    def id(self) -> str | None:
        return getattr(self._observation, "id", None)

    def update(self, **fields: Any) -> None:
        try:
            self._observation.update(**fields)
        except Exception:
            logger.warning("langfuse: could not update an observation", exc_info=True)


class LangfuseTracer:
    """Tracing on Langfuse through its OpenTelemetry-based SDK.

    Observations nest through the OpenTelemetry context, which follows `await`, so a span
    opened inside another one is its child without passing it around.
    """

    enabled = True

    def __init__(self, client: Langfuse) -> None:
        self.client = client

    def trace_id(self, seed: str) -> str | None:
        return Langfuse.create_trace_id(seed=seed)

    @contextlib.contextmanager
    def observe(
        self,
        name: str,
        *,
        as_type: str = "span",
        trace_id: str | None = None,
        **fields: Any,
    ) -> Iterator[Observation]:
        context = {"trace_id": trace_id} if trace_id else None
        with _guarded(
            lambda: self.client.start_as_current_observation(
                trace_context=context, name=name, as_type=as_type, **fields
            )
        ) as started:
            observation = (
                NULL_OBSERVATION if started is None else _LangfuseObservation(started)
            )
            try:
                yield observation
            except BaseException as error:
                observation.update(
                    level="ERROR", status_message=str(error) or type(error).__name__
                )
                raise

    @contextlib.contextmanager
    def attributes(
        self, *, metadata: dict[str, str], tags: list[str], trace_name: str
    ) -> Iterator[None]:
        with _guarded(
            lambda: propagate_attributes(
                metadata=metadata, tags=tags, trace_name=trace_name
            )
        ):
            yield None

    async def create_dataset(
        self, name: str, *, description: str, metadata: dict[str, Any]
    ) -> str | None:
        try:
            dataset = await self.client.async_api.datasets.create(
                name=name, description=description, metadata=metadata
            )
        except Exception:
            logger.warning("langfuse: could not create dataset %r", name, exc_info=True)
            return None
        return dataset.id

    async def upsert_dataset_item(
        self,
        dataset_name: str,
        item_id: str,
        *,
        input: Any,
        expected_output: Any,
        metadata: dict[str, Any],
    ) -> bool:
        try:
            await self.client.async_api.dataset_items.create(
                dataset_name=dataset_name,
                id=item_id,
                input=input,
                expected_output=expected_output,
                metadata=metadata,
            )
        except Exception:
            logger.warning(
                "langfuse: could not write dataset item %s", item_id, exc_info=True
            )
            return False
        return True

    async def link_dataset_run(
        self,
        run_name: str,
        item_id: str,
        *,
        trace_id: str,
        observation_id: str | None,
        metadata: dict[str, Any],
    ) -> None:
        try:
            await self.client.async_api.dataset_run_items.create(
                run_name=run_name,
                dataset_item_id=item_id,
                trace_id=trace_id,
                observation_id=observation_id,
                metadata=metadata,
            )
        except Exception:
            logger.warning(
                "langfuse: could not link trace %s to run %r",
                trace_id,
                run_name,
                exc_info=True,
            )

    async def flush(self) -> None:
        try:
            await asyncio.to_thread(self.client.flush)
        except Exception:
            logger.warning("langfuse: flush failed", exc_info=True)

    async def shutdown(self) -> None:
        try:
            await asyncio.to_thread(self.client.shutdown)
        except Exception:
            logger.warning("langfuse: shutdown failed", exc_info=True)

    async def check(self) -> bool:
        try:
            return bool(await asyncio.to_thread(self.client.auth_check))
        except Exception:
            logger.warning("langfuse: credentials check failed", exc_info=True)
            return False


@contextlib.contextmanager
def _guarded(
    factory: Callable[[], contextlib.AbstractContextManager[Any]],
) -> Iterator[Any]:
    """Enter a context manager of the SDK without letting its own failures escape.

    Yields `None` when it could not be entered. An exception of the enclosed block is
    passed to the manager, so the observation records it, and then raised as it was.
    """
    try:
        manager = factory()
        value = manager.__enter__()
    except Exception:
        logger.warning("langfuse: could not open an observation", exc_info=True)
        yield None
        return
    try:
        yield value
    except BaseException as error:
        _exit(manager, error)
        raise
    else:
        _exit(manager, None)


def _exit(
    manager: contextlib.AbstractContextManager[Any], error: BaseException | None
) -> None:
    try:
        if error is None:
            manager.__exit__(None, None, None)
        else:
            manager.__exit__(type(error), error, error.__traceback__)
    except Exception:
        logger.warning("langfuse: could not close an observation", exc_info=True)


def build_tracer(settings: Settings) -> Tracer:
    """The Langfuse tracer when both keys are configured, the null tracer otherwise."""
    if not settings.langfuse_enabled:
        return NULL_TRACER
    try:
        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            environment=settings.langfuse_environment,
            timeout=settings.langfuse_timeout_s,
        )
    except Exception:
        logger.warning("langfuse: client not created, tracing is off", exc_info=True)
        return NULL_TRACER
    return LangfuseTracer(client)


_tracer: Tracer | None = None


def get_tracer() -> Tracer:
    """The process-wide tracer, built from the settings on first use."""
    global _tracer
    if _tracer is None:
        _tracer = build_tracer(get_settings())
    return _tracer


def set_tracer(tracer: Tracer | None) -> None:
    """Replace the process-wide tracer; `None` builds it again from the settings."""
    global _tracer
    _tracer = tracer


def trace_url(trace_id: str | None, host: str) -> str | None:
    """Link to a trace in the Langfuse UI, which resolves the project from the trace."""
    if not trace_id:
        return None
    return f"{host.rstrip('/')}/trace/{trace_id}"
