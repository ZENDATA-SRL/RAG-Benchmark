from uuid import UUID

from fastapi import APIRouter

from config.solver.schemas import SolverConfigSchema
from config.solver.service import get_solver_by_id, resolve_solver

router = APIRouter(prefix="/config/solver", tags=["solver"])


@router.post("/solver")
async def resolve_solver_route(solver: SolverConfigSchema):
    return await resolve_solver(solver)


@router.get("/solver/{solver_id}")
async def get_solver_route(solver_id: UUID):
    return await get_solver_by_id(solver_id)
