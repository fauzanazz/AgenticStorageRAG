"""FastAPI application factory.

Creates and configures the FastAPI application instance.
Use create_app() to get a fully configured application.
"""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.infra.database import init_db, close_db
from app.infra.neo4j_client import neo4j_client
from app.infra.redis_client import redis_client
from app.infra.storage import storage_client
from app.infra.llm import llm_provider
from app.infra.middleware import RequestLoggingMiddleware
from app.domain.auth.router import router as auth_router
from app.domain.documents.router import router as documents_router
from app.domain.knowledge.router import router as knowledge_router
from app.domain.agents.router import router as agents_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Handles startup and shutdown events for external connections
    (database, Neo4j, Redis, Storage, LLM).
    """
    settings = get_settings()
    logger.info("Starting %s v%s (%s)", settings.app_name, settings.app_version, settings.environment)

    # Initialize infrastructure (order matters for dependencies)
    init_db()
    logger.info("Database engine initialized")

    try:
        await neo4j_client.connect()
    except Exception as e:
        logger.warning("Neo4j connection failed (non-fatal): %s", e)

    try:
        await redis_client.connect()
    except Exception as e:
        logger.warning("Redis connection failed (non-fatal): %s", e)

    try:
        storage_client.connect()
    except Exception as e:
        logger.warning("Supabase Storage connection failed (non-fatal): %s", e)

    llm_provider.initialize()

    yield

    # Shutdown infrastructure
    await close_db()
    await neo4j_client.close()
    await redis_client.close()
    logger.info("Application shutdown complete")


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

    # Middleware (order: last added = first executed)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoint with full service status
    @app.get(f"{settings.api_prefix}/health")
    async def health_check() -> dict[str, Any]:
        """Health check endpoint for monitoring and load balancers."""
        return {
            "status": "healthy",
            "version": settings.app_version,
            "environment": settings.environment,
        }

    @app.get(f"{settings.api_prefix}/health/detailed")
    async def detailed_health_check() -> dict[str, Any]:
        """Detailed health check with all service statuses."""
        neo4j_status = await neo4j_client.health_check()
        redis_status = await redis_client.health_check()
        llm_status = llm_provider.health_check()

        all_healthy = (
            neo4j_status.get("status") == "healthy"
            and redis_status.get("status") == "healthy"
        )

        return {
            "status": "healthy" if all_healthy else "degraded",
            "version": settings.app_version,
            "environment": settings.environment,
            "services": {
                "database": {"status": "configured"},
                "neo4j": neo4j_status,
                "redis": redis_status,
                "llm": llm_status,
            },
        }

    # Domain routers
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(documents_router, prefix=settings.api_prefix)
    app.include_router(knowledge_router, prefix=settings.api_prefix)
    app.include_router(agents_router, prefix=settings.api_prefix)

    # TODO: Include remaining domain routers
    # app.include_router(ingestion_router, prefix=settings.api_prefix)

    return app


app = create_app()
