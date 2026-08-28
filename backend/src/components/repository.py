from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.models import Component, ComponentVersion
from src.infrastructure.database.enums import ComponentType


class ComponentRepository:
    """Data access for `components`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, component: Component) -> Component:
        self.session.add(component)
        return component

    async def get_by_id(self, component_id: uuid.UUID) -> Component | None:
        return await self.session.get(Component, component_id)

    async def get_by_type_and_key(
        self, component_type: ComponentType, key: str
    ) -> Component | None:
        """Look a component up by its natural key, the pair backing the get-or-create."""
        statement = select(Component).where(
            Component.type == component_type, Component.key == key
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_by_type(self, component_type: ComponentType | None = None) -> Sequence[Component]:
        """List components, optionally of one type, ordered by type then key.

        The order is stable and not by creation date because this feeds the UI dropdowns:
        seeding a new component must not reshuffle the list the user already knows.
        """
        statement = select(Component).order_by(Component.type, Component.key)
        if component_type is not None:
            statement = statement.where(Component.type == component_type)
        return (await self.session.execute(statement)).scalars().all()


class ComponentVersionRepository:
    """Data access for `component_versions`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, version: ComponentVersion) -> ComponentVersion:
        self.session.add(version)
        return version

    async def get_version(self, version_id: uuid.UUID) -> ComponentVersion | None:
        return await self.session.get(ComponentVersion, version_id)

    async def get_version_by_component_and_version(
        self, component_id: uuid.UUID, version: str
    ) -> ComponentVersion | None:
        """Look a version up by its natural key `(component_id, version)`."""
        statement = select(ComponentVersion).where(
            ComponentVersion.component_id == component_id,
            ComponentVersion.version == version,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_versions(
        self, component_id: uuid.UUID, *, only_available: bool = False
    ) -> Sequence[ComponentVersion]:
        """List the versions of a component.

        Args:
            component_id: Component whose versions are listed.
            only_available: Keep just the versions that can currently be executed; an
                unavailable one stays in the table with its reason.
        """
        statement = (
            select(ComponentVersion)
            .where(ComponentVersion.component_id == component_id)
            .order_by(ComponentVersion.version)
        )
        if only_available:
            statement = statement.where(ComponentVersion.is_available.is_(True))
        return (await self.session.execute(statement)).scalars().all()
