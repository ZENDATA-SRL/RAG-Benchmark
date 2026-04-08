import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.base import Base


class EmbeddingConfig(Base):
    __tablename__ = "embedding_configs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)

    rag_configs: Mapped[list["RAGConfig"]] = relationship(back_populates="embedder")
    embeddings: Mapped[list["Embedding"]] = relationship(back_populates="embedder")
