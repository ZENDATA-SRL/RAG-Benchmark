from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from src.components.models import Component
from src.core.get_or_create import get_or_create
from src.infrastructure.database.enums import ComponentType

pytestmark = pytest.mark.integration


async def _get_or_create_component(session, key: str) -> Component:
    """Get-or-create a component on the natural key `(type, key)`."""

    async def lookup() -> Component | None:
        statement = select(Component).where(
            Component.type == ComponentType.PARSER, Component.key == key
        )
        return (await session.execute(statement)).scalar_one_or_none()

    async def create() -> Component:
        component = Component(
            type=ComponentType.PARSER, key=key, display_name=f"probe {key}"
        )
        session.add(component)
        await session.flush()
        return component

    return await get_or_create(session, lookup=lookup, create=create)


async def test_get_or_create_creates_once(session) -> None:
    key = f"probe-{uuid.uuid4().hex[:8]}"

    first = await _get_or_create_component(session, key)
    second = await _get_or_create_component(session, key)

    assert first.id == second.id


async def test_get_or_create_returns_existing_without_insert(session) -> None:
    """A second call must not add a row, or the seed would grow at every startup."""
    key = f"probe-{uuid.uuid4().hex[:8]}"

    await _get_or_create_component(session, key)
    await _get_or_create_component(session, key)

    statement = select(Component).where(
        Component.type == ComponentType.PARSER, Component.key == key
    )
    assert len((await session.execute(statement)).scalars().all()) == 1


async def test_get_or_create_survives_a_concurrent_writer(engine: AsyncEngine) -> None:
    """Two writers racing on the same key produce one row and no error.

    This test cannot use the shared transactional `session` fixture: the race only exists
    across two real transactions, so both writers commit and the row is cleaned up by hand.
    """
    key = f"race-{uuid.uuid4().hex[:8]}"
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async def writer() -> uuid.UUID:
        async with factory() as session:
            async with session.begin():
                component = await _get_or_create_component(session, key)
                return component.id

    try:
        first_id, second_id = await asyncio.gather(writer(), writer())

        assert first_id == second_id

        async with factory() as session:
            statement = select(Component).where(
                Component.type == ComponentType.PARSER, Component.key == key
            )
            assert len((await session.execute(statement)).scalars().all()) == 1
    finally:
        async with factory() as session:
            async with session.begin():
                statement = select(Component).where(
                    Component.type == ComponentType.PARSER, Component.key == key
                )
                for component in (await session.execute(statement)).scalars().all():
                    await session.delete(component)
