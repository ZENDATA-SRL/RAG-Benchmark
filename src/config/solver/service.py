from uuid import UUID

from src.config.solver.repository import get_solver_repository
from src.config.solver.schemas import SolverConfig, SolverConfigSchema


async def resolve_solver(solver: SolverConfigSchema) -> SolverConfig:
    repository = get_solver_repository()
    solver_object = await repository.get_solver_by_config(solver)
    if solver_object:
        return SolverConfig.model_validate(solver_object)
    created = await repository.insert_solver_config(solver)
    return SolverConfig.model_validate(created)


async def get_solver_by_id(solver_id: UUID) -> SolverConfig:
    repository = get_solver_repository()
    obj = await repository.get_solver_by_id(solver_id)
    if obj is None:
        raise ValueError(f"Solver config {solver_id} not found")
    return SolverConfig.model_validate(obj)
