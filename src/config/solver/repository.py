from config.solver.models import SolverConfig
from config.solver.schemas import SolverConfigSchema


class SolverRepository:
    async def get_solver_by_config(
        self, solver: SolverConfigSchema
    ) -> SolverConfig | None:
        pass

    async def insert_solver_config(self, solver: SolverConfigSchema) -> SolverConfig:
        pass


def get_solver_repository() -> SolverRepository:
    return SolverRepository()
