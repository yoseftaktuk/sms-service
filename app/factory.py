from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.database import engine


def _default_lifespan_context() -> Callable:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    return lifespan


def create_app(*, lifespan: Callable | None = None) -> FastAPI:
    app = FastAPI(
        title="SMS Service",
        description="Nedarim Plus transaction webhook",
        version="1.0.0",
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan or _default_lifespan_context(),
    )
    app.include_router(api_router, prefix="/api/v1")
    return app
