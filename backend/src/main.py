from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.infrastructure.database.session import dispose_engine
from src.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    """Build the FastAPI application and register its routers."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
