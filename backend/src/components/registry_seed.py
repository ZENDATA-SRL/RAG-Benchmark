from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.components.builtin import BUILTIN_DESCRIPTORS
from src.components.service import ComponentService
from src.infrastructure.database.enums import RuntimeType

logger = logging.getLogger(__name__)


async def seed_builtin_components(session: AsyncSession) -> None:
    """Register the declared builtin components, idempotently.

    Runs at every startup and is safe to repeat: both writes go through the get-or-create
    of `ComponentService`, keyed on `(type, key)` and `(component_id, version)`, so a
    restart reuses the existing rows and the profiles that reference them keep pointing at
    the same version ids.

    Driven by the descriptors and not by the implementations: the API seeds and serves the
    registry without importing the parsing code, which only the Temporal worker executes.

    Args:
        session: Session owning the transaction; the caller commits.
    """
    service = ComponentService(session)

    for descriptor in BUILTIN_DESCRIPTORS:
        component = await service.register_component(
            descriptor.component_type, descriptor.key, descriptor.display_name
        )
        await service.register_version(
            component_id=component.id,
            version=descriptor.version,
            runtime=RuntimeType.BUILTIN,
            params_schema=descriptor.params_schema,
            capabilities=descriptor.capabilities,
        )

    logger.info(
        "builtin registry seeded: %s",
        ", ".join(
            f"{descriptor.component_type.value}/{descriptor.key} v{descriptor.version}"
            for descriptor in BUILTIN_DESCRIPTORS
        ),
    )
