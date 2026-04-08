from uuid import UUID
from config.solver.models import SolverConfigORM
from config.solver.schemas import SolverConfigSchema
from infrastructure.database.db import get_sessionmaker

from sqlalchemy import select


class SolverRepository:
    async def get_solver_by_id(self, solver_id: UUID) -> SolverConfigORM | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            return await session.get(SolverConfigORM, solver_id)

    async def get_solver_by_config(
        self, solver: SolverConfigSchema
    ) -> SolverConfigORM | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            stmt = (
                select(SolverConfigORM)
                .where(SolverConfigORM.top_k == solver.top_k)
                .where(SolverConfigORM.reranking == (solver.reranking or "semantic"))
                .where(SolverConfigORM.hyde == solver.hyde)
                .where(SolverConfigORM.hybrid == solver.hybrid)
                .where(SolverConfigORM.strategy == (solver.strategy or ""))
                .limit(1)
            )
            return await session.scalar(stmt)

    async def insert_solver_config(self, solver: SolverConfigSchema) -> SolverConfigORM:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            obj = SolverConfigORM(
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
