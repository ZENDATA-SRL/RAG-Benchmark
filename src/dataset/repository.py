from uuid import UUID

from sqlalchemy import select

from src.dataset.models import DatasetORM, DocumentORM, QuestionORM
from src.infrastructure.database.db import get_sessionmaker


async def get_document(document_id: UUID) -> DocumentORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        return await session.get(DocumentORM, document_id)


async def get_documents_by_dataset(dataset_id: UUID) -> list[DocumentORM]:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(DocumentORM)
            .where(DocumentORM.dataset_id == dataset_id)
            .order_by(DocumentORM.name.asc())
        )
        rows = (await session.scalars(stmt)).all()
        return list(rows)


async def find_document_by_name_and_url(
    name: str, url: str, dataset_id: UUID
) -> DocumentORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(DocumentORM)
            .where(DocumentORM.name == name)
            .where(DocumentORM.url == url)
            .where(DocumentORM.dataset_id == dataset_id)
            .limit(1)
        )
        return await session.scalar(stmt)


async def insert_document(document: DocumentORM) -> None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(document)
        await session.commit()
        await session.refresh(document)


async def get_dataset(dataset_id: UUID) -> DatasetORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        return await session.get(DatasetORM, dataset_id)


async def get_datasets() -> list[DatasetORM]:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = select(DatasetORM).order_by(DatasetORM.created_at.desc())
        rows = (await session.scalars(stmt)).all()
        return list(rows)


async def delete_dataset(dataset_id: UUID) -> bool:
    """
    Deletes the dataset row. Related documents/questions/scans/chunks/embeddings
    are removed via SQLAlchemy relationship cascades + DB FK cascades.
    """
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        obj = await session.get(DatasetORM, dataset_id)
        if obj is None:
            return False
        await session.delete(obj)
        await session.commit()
        return True


async def get_question(question_id: UUID) -> QuestionORM | None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        return await session.get(QuestionORM, question_id)


async def get_questions_by_dataset(dataset_id: UUID) -> list[QuestionORM]:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        stmt = (
            select(QuestionORM)
            .where(QuestionORM.dataset_id == dataset_id)
            .order_by(QuestionORM.id.asc())
        )
        rows = (await session.scalars(stmt)).all()
        return list(rows)


async def insert_dataset(dataset: DatasetORM) -> None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(dataset)
        await session.commit()
        await session.refresh(dataset)


async def insert_question(question: QuestionORM) -> None:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(question)
        await session.commit()
        await session.refresh(question)
