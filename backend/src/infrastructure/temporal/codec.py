from __future__ import annotations

import dataclasses
from collections.abc import Sequence

from temporalio.api.common.v1 import Payload
from temporalio.converter import DataConverter, PayloadCodec
from temporalio.converter import default as default_converter

# 128 KB: a comfortable ceiling for the ids, hashes and counts the activities exchange, and
# far below the megabytes a page of PDF text would take. The number is a guard, not a tuning
# knob — see the class docstring.
MAX_PAYLOAD_BYTES = 128 * 1024


class PayloadTooLargeError(Exception):
    """Raised when a workflow or activity payload exceeds `MAX_PAYLOAD_BYTES`."""

    def __init__(self, size: int, limit: int) -> None:
        super().__init__(
            f"payload of {size} bytes exceeds the {limit} byte limit; "
            "pass a storage reference, not the content"
        )
        self.size = size
        self.limit = limit


class SizeGuardCodec(PayloadCodec):
    """A codec that refuses payloads above a hard size threshold (RT-O02).

    It encodes nothing — the bytes pass through unchanged — but it is the mechanical guard
    that stops the day someone passes the full text of a 300-page PDF to an activity. Such a
    payload would bloat Temporal's history irrecoverably; failing loudly at the boundary is
    cheaper than discovering it as an unexplained slowdown weeks later. Artefacts travel as
    storage URIs, never as content.
    """

    def __init__(self, limit: int = MAX_PAYLOAD_BYTES) -> None:
        self._limit = limit

    async def encode(self, payloads: Sequence[Payload]) -> list[Payload]:
        for payload in payloads:
            size = len(payload.data)
            if size > self._limit:
                raise PayloadTooLargeError(size, self._limit)
        return list(payloads)

    async def decode(self, payloads: Sequence[Payload]) -> list[Payload]:
        return list(payloads)


def data_converter() -> DataConverter:
    """The data converter every client and worker shares.

    Wraps the default converter with `SizeGuardCodec`, so the payload size limit of RT-O02
    is enforced by the transport itself and cannot be forgotten at a call site — including
    when the caller is the API rather than an activity.
    """
    return dataclasses.replace(default_converter(), payload_codec=SizeGuardCodec())
