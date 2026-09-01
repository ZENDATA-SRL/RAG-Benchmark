from __future__ import annotations

from src.infrastructure.temporal.codec import (
    MAX_PAYLOAD_BYTES,
    PayloadTooLargeError,
    SizeGuardCodec,
)

# The guard lives in the backend because the API is also a Temporal client and must encode
# payloads the same way the worker does; re-exported here so worker code keeps importing it
# from its own package.
__all__ = ["MAX_PAYLOAD_BYTES", "PayloadTooLargeError", "SizeGuardCodec"]
