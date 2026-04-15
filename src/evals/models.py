import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import Base


class EvaluatorORM(Base):
    __tablename__ = "evaluators"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.now
    )
    scores: Mapped[list["ScoreORM"]] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="evaluator", cascade="all, delete-orphan"
    )


class ScoreORM(Base):
    __tablename__ = "scores"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    trace_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("traces.id", ondelete="CASCADE"),
        nullable=False,
    )
    evaluator_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("evaluators.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.now
    )

    evaluator: Mapped["EvaluatorORM"] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="scores"
    )
    trace: Mapped["TraceORM"] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="scores"
    )


class TraceORM(Base):
    __tablename__ = "traces"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    answer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("answers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    langfuse_trace_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.now
    )

    answer: Mapped["AnswerORM"] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="trace"
    )
    scores: Mapped[list["ScoreORM"]] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="trace", cascade="all, delete-orphan"
    )
