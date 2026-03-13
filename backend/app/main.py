"""FastAPI application factory.

Creates and configures the FastAPI application instance.
Use create_app() to get a fully configured application.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Handles startup and shutdown events for external connections
    (database, Neo4j, Redis, etc.).
    """
    settings = get_settings()
    # TODO: Initialize database engine
    # TODO: Initialize Neo4j driver
    # TODO: Initialize Redis client
    # TODO: Initialize background worker
    yield
    # TODO: Close database engine
    # TODO: Close Neo4j driver
    # TODO: Close Redis client


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoint
    @app.get(f"{settings.api_prefix}/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint for monitoring and load balancers."""
        return {
            "status": "healthy",
            "version": settings.app_version,
            "environment": settings.environment,
        }

    # TODO: Include domain routers
    # app.include_router(auth_router, prefix=settings.api_prefix)
    # app.include_router(documents_router, prefix=settings.api_prefix)
    # app.include_router(knowledge_router, prefix=settings.api_prefix)
    # app.include_router(agents_router, prefix=settings.api_prefix)
    # app.include_router(ingestion_router, prefix=settings.api_prefix)

    return app


app = create_app()
