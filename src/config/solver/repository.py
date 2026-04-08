from uuid import UUID
from config.solver.models import SolverConfig
from config.solver.schemas import SolverConfigSchema
from infrastructure.database.db import get_sessionmaker

from sqlalchemy import select


class SolverRepository:
    async def get_solver_by_id(self, solver_id: UUID) -> SolverConfig | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            return await session.get(SolverConfig, solver_id)

    async def get_solver_by_config(
        self, solver: SolverConfigSchema
    ) -> SolverConfig | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            stmt = (
                select(SolverConfig)
                .where(SolverConfig.top_k == solver.top_k)
                .where(SolverConfig.reranking == (solver.reranking or "semantic"))
                .where(SolverConfig.hyde == solver.hyde)
                .where(SolverConfig.hybrid == solver.hybrid)
                .where(SolverConfig.strategy == (solver.strategy or ""))
                .limit(1)
            )
            return await session.scalar(stmt)

    async def insert_solver_config(self, solver: SolverConfigSchema) -> SolverConfig:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            obj = SolverConfig(
                top_k=solver.top_k,
                reranking=solver.reranking or "semantic",
                hyde=solver.hyde,
                hybrid=solver.hybrid,
                strategy=solver.strategy or "",
            )
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj


def get_solver_repository() -> SolverRepository:
    return SolverRepository()
