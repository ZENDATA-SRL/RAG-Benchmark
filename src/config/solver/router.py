from uuid import UUID

from fastapi import APIRouter

from src.config.solver.schemas import SolverConfig, SolverConfigSchema
from src.config.solver.service import get_solver_by_id, resolve_solver

router = APIRouter(prefix="/solver", tags=["solver"])


@router.post("")
async def resolve_solver_route(solver: SolverConfigSchema) -> SolverConfig:
    return await resolve_solver(solver)


@router.get("/{solver_id}")
async def get_solver_route(solver_id: UUID) -> SolverConfig:
    return await get_solver_by_id(solver_id)
