from __future__ import annotations

from collections.abc import Sequence
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class Page(BaseModel, Generic[T]):
    """One window over a listing, together with the size of the whole result set.

    `total` is returned alongside the window because the UI needs the number of pages
    before it can render a pager, and counting client-side is impossible once the result
    is truncated.
    """

    items: list[T] = Field(default_factory=list)
    total: int
    limit: int
    offset: int

    @classmethod
    def build(cls, items: Sequence[T], *, total: int, limit: int, offset: int) -> Page[T]:
        """Assemble a page from a repository window and its total count."""
        return cls(items=list(items), total=total, limit=limit, offset=offset)
