from uuid import UUID

from benchmark.models import Document


async def get_document(document_id: UUID) -> Document | None:
    pass


async def insert_document(document: Document) -> None:
    pass
