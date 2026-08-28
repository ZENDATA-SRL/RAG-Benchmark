from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_session
from src.infrastructure.storage import ObjectStorage, get_object_storage
from src.settings import Settings, get_settings

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_storage(settings: SettingsDep) -> ObjectStorage:
    """Return the shared object storage client for the request."""
    return get_object_storage(settings)


StorageDep = Annotated[ObjectStorage, Depends(get_storage)]
