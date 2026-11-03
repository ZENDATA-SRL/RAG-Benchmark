from __future__ import annotations


def zones(chunk_count: int, count: int) -> list[range]:
    """Split the chunks of a document, by ordinal, into `count` contiguous zones.

    Asking for one question per zone spreads the questions over the whole document;
    left alone, a model writes them about the first pages. Zones differ in size by one
    chunk at most, and there are never more zones than chunks.
    """
    count = max(1, min(count, chunk_count))
    if chunk_count <= 0:
        return []
    size, extra = divmod(chunk_count, count)
    result = []
    start = 0
    for index in range(count):
        end = start + size + (1 if index < extra else 0)
        result.append(range(start, end))
        start = end
    return result


def zone_of(ordinal: int, chunk_zones: list[range]) -> int | None:
    """The 1-based zone a chunk falls in, or `None` outside every zone."""
    for index, zone in enumerate(chunk_zones, start=1):
        if ordinal in zone:
            return index
    return None
