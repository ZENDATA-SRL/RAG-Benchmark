from config.solver.models import SolverConfig
from config.solver.repository import get_solver_repository
from config.solver.schemas import SolverConfigSchema


async def resolve_solver(solver: SolverConfigSchema) -> SolverConfig:
    repository = get_solver_repository()
    solver_object = await repository.get_solver_by_config(solver)
    if solver_object:
        return solver_object
    solver_config = SolverConfigSchema(strategy=solver.strategy)
    return await repository.insert_solver_config(solver_config)
