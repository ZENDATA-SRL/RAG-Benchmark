from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar

# A ContextVar rather than a parameter threaded through every call: the request id has to
# reach the repository layer, and passing it explicitly would put an HTTP concern in every
# signature. asyncio copies the context per task, so concurrent requests stay isolated.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Inject the current request id into every record so the format string can use it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def new_request_id() -> str:
    """Return a fresh request id."""
    return uuid.uuid4().hex


def bind_request_id(request_id: str) -> None:
    """Bind a request id to the current async context."""
    request_id_var.set(request_id)


def get_request_id() -> str:
    """Return the request id bound to the current async context, or `-`."""
    return request_id_var.get()


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger once, with the request id in the format.

    Idempotent: repeated calls (multiple workers, or tests re-creating the app) replace the
    handler instead of stacking duplicates that would print every line several times.

    Args:
        level: Logging level name, e.g. `INFO` or `DEBUG`.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
