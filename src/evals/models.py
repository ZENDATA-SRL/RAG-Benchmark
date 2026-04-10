import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import Base


class RagEvaluationORM(Base):
    __tablename__ = "rag_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.now
    )

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
    )

    experiment: Mapped["ExperimentORM"] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="rag_evaluations"
    )


class LangfuseEvaluationORM(Base):
    __tablename__ = "langfuse_evaluations"

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.now
    )

    # NOTE: I don't know Langfuse's score object yet.

    experiment: Mapped["ExperimentORM"] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="langfuse_evaluation"
    )
