from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.answering.chat_models import missing_credentials
from src.components.builtin import ANSWER_SYSTEM_DESCRIPTORS
from src.components.registry_seed import seed_builtin_components
from src.components.repository import ComponentRepository, ComponentVersionRepository
from src.components.service import ComponentService

logger = logging.getLogger(__name__)


async def sync_answer_system_availability(session: AsyncSession) -> None:
    """Mark each builtin answer system available or not, from this process's credentials.

    Run by the worker at startup, since the model credentials live in the worker's
    environment and not in the API's. A version is available when at least one of its
    providers has credentials; a profile on a provider without them fails its executions
    with the reason. The registry is seeded first, so the worker does not depend on the API
    having started.

    Args:
        session: Session owning the transaction; the caller commits.
    """
    await seed_builtin_components(session)
    service = ComponentService(session)
    components = ComponentRepository(session)
    versions = ComponentVersionRepository(session)
    for descriptor in ANSWER_SYSTEM_DESCRIPTORS:
        component = await components.get_by_type_and_key(
            descriptor.component_type, descriptor.key
        )
        version = await versions.get_version_by_component_and_version(
            component.id, descriptor.version
        )
        providers = descriptor.params_schema["properties"]["provider"]["enum"]
        missing = {
            provider: reason
            for provider in providers
            if (reason := missing_credentials(provider)) is not None
        }
        reason = "; ".join(f"{provider}: {text}" for provider, text in missing.items())
        if len(missing) == len(providers):
            await service.mark_unavailable(version.id, reason)
        else:
            await service.mark_available(version.id)
        logger.info(
            "answer system %s@%s available=%s missing=%s",
            descriptor.key,
            descriptor.version,
            version.is_available,
            reason or "-",
        )
