from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from src.components.schemas import (
    ComponentCreate,
    ComponentRead,
    ComponentVersionCreate,
    ComponentVersionRead,
    ComponentVersionUnavailable,
    ComponentWithVersionsRead,
)
from src.components.service import ComponentService
from src.dependencies import SessionDep
from src.infrastructure.database.enums import ComponentType

router = APIRouter(prefix="/components", tags=["components"])


@router.get("", response_model=list[ComponentWithVersionsRead])
async def list_components(
    session: SessionDep,
    component_type: ComponentType | None = Query(default=None, alias="type"),
    only_available: bool = Query(default=False),
) -> list[ComponentWithVersionsRead]:
    """List the registered components with their versions and JSON Schemas."""
    service = ComponentService(session)
    components = await service.list_components(component_type)
    return [
        ComponentWithVersionsRead(
            **ComponentRead.model_validate(component).model_dump(),
            versions=[
                ComponentVersionRead.model_validate(version)
                for version in await service.list_versions(
                    component.id, only_available=only_available
                )
            ],
        )
        for component in components
    ]


@router.get("/{component_id}/versions", response_model=list[ComponentVersionRead])
async def list_component_versions(
    component_id: uuid.UUID,
    session: SessionDep,
    only_available: bool = Query(default=False),
) -> list[ComponentVersionRead]:
    """List the versions of a component."""
    versions = await ComponentService(session).list_versions(
        component_id, only_available=only_available
    )
    return [ComponentVersionRead.model_validate(version) for version in versions]


@router.post("", response_model=ComponentRead, status_code=status.HTTP_201_CREATED)
async def create_component(payload: ComponentCreate, session: SessionDep) -> ComponentRead:
    """Register a component, returning the existing one if it is already known."""
    component = await ComponentService(session).register_component(
        payload.type, payload.key, payload.display_name
    )
    return ComponentRead.model_validate(component)


@router.post(
    "/{component_id}/versions",
    response_model=ComponentVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_component_version(
    component_id: uuid.UUID, payload: ComponentVersionCreate, session: SessionDep
) -> ComponentVersionRead:
    """Register a version of a component."""
    version = await ComponentService(session).register_version(
        component_id=component_id,
        version=payload.version,
        runtime=payload.runtime,
        endpoint=payload.endpoint,
        params_schema=payload.params_schema,
        capabilities=payload.capabilities,
    )
    return ComponentVersionRead.model_validate(version)


@router.post("/versions/{version_id}/unavailable", response_model=ComponentVersionRead)
async def mark_version_unavailable(
    version_id: uuid.UUID, payload: ComponentVersionUnavailable, session: SessionDep
) -> ComponentVersionRead:
    """Exclude a version from the available choices, recording the reason."""
    version = await ComponentService(session).mark_unavailable(version_id, payload.reason)
    return ComponentVersionRead.model_validate(version)


@router.post("/versions/{version_id}/available", response_model=ComponentVersionRead)
async def mark_version_available(
    version_id: uuid.UUID, session: SessionDep
) -> ComponentVersionRead:
    """Make a previously excluded version available again."""
    version = await ComponentService(session).mark_available(version_id)
    return ComponentVersionRead.model_validate(version)
