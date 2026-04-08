import uuid

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.base import Base


class ChunkerConfig(Base):
    __tablename__ = "chunker_configs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy: Mapped[str] = mapped_column(String, nullable=False, default="")
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    overlap_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    rag_configs: Mapped[list["RAGConfig"]] = relationship(back_populates="chunker")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="chunker")
