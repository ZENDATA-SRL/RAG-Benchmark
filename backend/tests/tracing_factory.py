from __future__ import annotations

import contextlib
import dataclasses
import types
from typing import Any


@dataclasses.dataclass
class FakeObservation:
    """An observation as the fake client records it, with the updates it received."""

    name: str
    as_type: str
    parent: str | None
    trace_context: dict[str, str] | None
    fields: dict[str, Any]
    updates: list[dict[str, Any]] = dataclasses.field(default_factory=list)

    @property
    def id(self) -> str:
        return f"obs-{self.name}"

    def update(self, **fields: Any) -> None:
        self.updates.append(fields)

    def updated(self, key: str) -> Any:
        """The last value an update gave to `key`."""
        values = [update[key] for update in self.updates if key in update]
        return values[-1] if values else None


class _Calls:
    def __init__(self, calls: list[dict[str, Any]], returns: Any = None) -> None:
        self.calls = calls
        self.returns = returns

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.returns


class FakeLangfuse:
    """Stands in for the Langfuse client: records observations and API calls, offline."""

    def __init__(self, *, fail_observations: bool = False) -> None:
        self.fail_observations = fail_observations
        self.observations: list[FakeObservation] = []
        self.propagated: list[dict[str, Any]] = []
        self.datasets: list[dict[str, Any]] = []
        self.items: list[dict[str, Any]] = []
        self.experiments: list[dict[str, Any]] = []
        self.flushed = 0
        self._stack: list[FakeObservation] = []
        self.async_api = types.SimpleNamespace(
            datasets=_Calls(self.datasets, types.SimpleNamespace(id="dataset-1")),
            dataset_items=_Calls(self.items),
        )

    def start_as_current_observation(
        self, *, trace_context, name: str, as_type: str, **fields: Any
    ):
        if self.fail_observations:
            raise RuntimeError("langfuse is down")
        observation = FakeObservation(
            name=name,
            as_type=as_type,
            parent=self._stack[-1].name if self._stack else None,
            trace_context=trace_context,
            fields=fields,
        )
        self.observations.append(observation)

        @contextlib.contextmanager
        def current():
            self._stack.append(observation)
            try:
                yield observation
            finally:
                self._stack.pop()

        return current()

    def named(self, name: str) -> list[FakeObservation]:
        return [item for item in self.observations if item.name == name]

    def flush(self) -> None:
        self.flushed += 1

    def shutdown(self) -> None:
        pass

    def auth_check(self) -> bool:
        return True
