from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.sources.models import ImportSelection
from src.sources.service import UploadImportService

logger = logging.getLogger(__name__)


async def seed_upload_source(session: AsyncSession) -> ImportSelection:
    """Register the singleton manual-upload connection and its selection, idempotently.

    Provenance is mandatory for every document, so the connection uploads are
    attributed to has to exist before the first upload. Seeding it at startup rather than
    lazily on first use keeps the row stable and visible in the sources listing from boot.

    Args:
        session: Session owning the transaction; the caller commits.

    Returns:
        The upload selection every manual import run hangs off.
    """
    selection = await UploadImportService(session).get_or_create_selection()
    logger.info("manual upload source seeded: selection %s", selection.id)
    return selection
