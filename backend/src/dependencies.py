from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
