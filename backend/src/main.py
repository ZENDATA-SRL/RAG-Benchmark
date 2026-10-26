from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.artifacts.router import router as artifacts_router
from src.components.registry_seed import seed_builtin_components
from src.components.router import router as components_router
from src.core.exceptions import DomainError
from src.core.logging import (
    bind_request_id,
    configure_logging,
    get_request_id,
    new_request_id,
)
from src.corpora.router import router as corpora_router
from src.documents.router import router as documents_router
from src.experiments.router import router as experiments_router
from src.experiments.seed import seed_metric_catalog
from src.indexes.router import router as indexes_router
from src.infrastructure.database.session import dispose_engine, session_factory
from src.infrastructure.temporal import reset_workflow_client
from src.materializations.router import router as materializations_router
from src.pipelines.router import router as pipelines_router
from src.qa_sets.router import router as qa_sets_router
from src.retrieval.router import router as retrieval_router
from src.settings import get_settings
from src.sources.seed import seed_upload_source

API_PREFIX = "/api/v1"
REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Seed the registry, the upload source and the metric catalog at startup, release the pool at shutdown."""
    async with session_factory() as session:
        await seed_builtin_components(session)
        await seed_upload_source(session)
        await seed_metric_catalog(session)
        await session.commit()
    yield
    await reset_workflow_client()
    await dispose_engine()


def create_app() -> FastAPI:
    """Build the FastAPI application and register its routers."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        """Bind a request id for the whole request and echo it back to the client.

        An id supplied by the caller is honoured so that a failure reported from the UI can
        be traced without correlating timestamps.
        """
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        bind_request_id(request_id)
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @app.exception_handler(DomainError)
    async def domain_error_handler(
        request: Request, error: DomainError
    ) -> JSONResponse:
        """Serialise every domain error into one shape, so the UI parses a single contract."""
        logger.info("domain error %s: %s", error.code, error.message)
        return JSONResponse(
            status_code=error.status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
            headers={REQUEST_ID_HEADER: get_request_id()},
        )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(components_router, prefix=API_PREFIX)
    app.include_router(corpora_router, prefix=API_PREFIX)
    app.include_router(documents_router, prefix=API_PREFIX)
    app.include_router(pipelines_router, prefix=API_PREFIX)
    app.include_router(artifacts_router, prefix=API_PREFIX)
    app.include_router(materializations_router, prefix=API_PREFIX)
    app.include_router(indexes_router, prefix=API_PREFIX)
    app.include_router(retrieval_router, prefix=API_PREFIX)
    app.include_router(qa_sets_router, prefix=API_PREFIX)
    app.include_router(experiments_router, prefix=API_PREFIX)

    return app


app = create_app()
