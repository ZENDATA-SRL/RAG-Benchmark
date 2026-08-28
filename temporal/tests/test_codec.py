from __future__ import annotations

import pytest
from temporalio.api.common.v1 import Payload

from temporal.codec import MAX_PAYLOAD_BYTES, PayloadTooLargeError, SizeGuardCodec

pytestmark = pytest.mark.asyncio


async def test_small_payload_passes_through_unchanged() -> None:
    codec = SizeGuardCodec()
    payload = Payload(data=b"small")
    assert await codec.encode([payload]) == [payload]
    assert await codec.decode([payload]) == [payload]


async def test_oversized_payload_is_rejected() -> None:
    codec = SizeGuardCodec(limit=16)
    with pytest.raises(PayloadTooLargeError):
        await codec.encode([Payload(data=b"x" * 32)])


async def test_default_limit_is_the_documented_guard() -> None:
    assert MAX_PAYLOAD_BYTES == 128 * 1024
