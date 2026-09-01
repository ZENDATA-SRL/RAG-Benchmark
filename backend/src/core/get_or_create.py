from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


async def get_or_create_reporting(
    session: AsyncSession,
    *,
    lookup: Callable[[], Awaitable[T | None]],
    create: Callable[[], Awaitable[T]],
) -> tuple[T, bool]:
    """Like `get_or_create`, but also report whether this call created the row.

    The flag exists because deduplication is invisible from the outside: a caller that
    creates the same content-addressed row under a new name gets the original row back, and
    the only way to explain the name it does not see is to say the row was already there.

    Args:
        session: Session owning the surrounding transaction.
        lookup: Coroutine returning the row for the key, or `None`.
        create: Coroutine inserting and flushing the row.

    Returns:
        The row and `True` only if this call inserted it; losing the race against a
        concurrent writer reports `False`, since the row is the winner's.

    Raises:
        IntegrityError: If the insert violated a constraint other than the key it is
            deduplicated on, in which case the lookup still finds nothing.
    """
    existing = await lookup()
    if existing is not None:
        return existing, False

    try:
        async with session.begin_nested():
            return await create(), True
    except IntegrityError:
        concurrent = await lookup()
        if concurrent is None:
            raise
        return concurrent, False


async def get_or_create(
    session: AsyncSession,
    *,
    lookup: Callable[[], Awaitable[T | None]],
    create: Callable[[], Awaitable[T]],
) -> T:
    """Return the existing row for a key, creating it only if absent.

    The creation runs inside a savepoint so that losing the race against a concurrent
    writer costs the savepoint and not the whole transaction: on unique violation the
    lookup is retried and the winner's row is returned.

    Args:
        session: Session owning the surrounding transaction.
        lookup: Coroutine returning the row for the key, or `None`.
        create: Coroutine inserting and flushing the row.

    Returns:
        The pre-existing row, the newly created one, or the one a concurrent writer
        created for the same key.

    Raises:
        IntegrityError: If the insert violated a constraint other than the key it is
            deduplicated on, in which case the lookup still finds nothing.
    """
    row, _ = await get_or_create_reporting(session, lookup=lookup, create=create)
    return row
