"""FastAPI application factory.

Creates and configures the FastAPI application instance.
Use create_app() to get a fully configured application.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.domain.agents.router import router as agents_router
from app.domain.auth.models import OAuthAccount  # noqa: F401 — needed for Alembic
from app.domain.auth.oauth.router import router as oauth_router
from app.domain.auth.router import router as auth_router
from app.domain.documents.router import router as documents_router
from app.domain.ingestion.router import router as ingestion_router
from app.domain.knowledge.router import router as knowledge_router
from app.domain.settings.models import UserModelSettings  # noqa: F401 — needed for Alembic
from app.domain.settings.router import router as settings_router
from app.infra.database import close_db, init_db
from app.infra.llm import llm_provider
from app.infra.middleware import RequestLoggingMiddleware
from app.infra.neo4j_client import neo4j_client
from app.infra.redis_client import redis_client
from app.infra.security_headers import SecurityHeadersMiddleware
from app.infra.storage import storage_client
from app.scripts.graph_schema import apply_schema

logger = logging.getLogger(__name__)

# Timeout (seconds) for each infra connect/close during lifespan.
# Prevents reload-triggered shutdowns from hanging indefinitely.
_SHUTDOWN_TIMEOUT = 5.0
_STARTUP_CONNECT_TIMEOUT = 10.0


async def _auto_seed_graph_if_empty() -> None:
    """Auto-seed the Neo4j graph from local seed files if the graph is empty.

    Only triggers when:
    1. Neo4j graph has zero nodes
    2. manifest.json exists with data files listed
    """
    import json
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parent.parent / "graph_seed" / "manifest.json"
    if not manifest_path.exists():
        return

    # Check if graph is empty
    get_settings()
    records = await neo4j_client.execute_read("MATCH (n) RETURN count(n) AS cnt LIMIT 1")
    node_count = records[0]["cnt"] if records else 0

    if node_count > 0:
        logger.debug("Neo4j graph has %d nodes, skipping auto-seed", node_count)
        return

    # Check if manifest has data
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entity_files = manifest.get("files", {}).get("entities", [])
    if not entity_files:
        logger.debug("No entity files in manifest, skipping auto-seed")
        return

    # Import
    logger.info(
        "Auto-seeding graph from local files (version %s, updated %s)",
        manifest.get("version"),
        manifest.get("updated_at"),
    )
    from app.scripts.graph_import import import_graph

    await import_graph(clean=False)
    logger.info("Auto-seed complete")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Handles startup and shutdown events for external connections
    (database, Neo4j, Redis, Storage, LLM).

    All connect/close calls are wrapped with timeouts so that
    uvicorn --reload never freezes waiting for a hung driver.
    """
    settings = get_settings()
    logger.info(
        "Starting %s v%s (%s)", settings.app_name, settings.app_version, settings.environment
    )

    # Initialize infrastructure (order matters for dependencies)
    init_db()
    logger.info("Database engine initialized")

    neo4j_connected = False
    try:
        await asyncio.wait_for(
            neo4j_client.connect(),
            timeout=_STARTUP_CONNECT_TIMEOUT,
        )
        neo4j_connected = True
    except TimeoutError:
        logger.warning(
            "Neo4j connection timed out after %.0fs (non-fatal)", _STARTUP_CONNECT_TIMEOUT
        )
    except Exception as e:
        logger.warning("Neo4j connection failed (non-fatal): %s", e)

    # Apply Neo4j schema (indexes/constraints) and auto-seed if graph is empty
    if neo4j_connected:
        try:
            await asyncio.wait_for(
                apply_schema(neo4j_client.driver),
                timeout=_STARTUP_CONNECT_TIMEOUT,
            )
            logger.info("Neo4j schema applied")
        except TimeoutError:
            logger.warning("Neo4j schema init timed out (non-fatal)")
        except Exception as e:
            logger.warning("Neo4j schema init failed (non-fatal): %s", e)

        try:
            await _auto_seed_graph_if_empty()
        except Exception as e:
            logger.warning("Neo4j auto-seed failed (non-fatal): %s", e)

    try:
        await asyncio.wait_for(
            redis_client.connect(),
            timeout=_STARTUP_CONNECT_TIMEOUT,
        )
    except TimeoutError:
        logger.warning(
            "Redis connection timed out after %.0fs (non-fatal)", _STARTUP_CONNECT_TIMEOUT
        )
    except Exception as e:
        logger.warning("Redis connection failed (non-fatal): %s", e)

    try:
        storage_client.connect()
        await storage_client.ensure_bucket()
    except Exception as e:
        logger.warning("Supabase Storage connection failed (non-fatal): %s", e)

    llm_provider.initialize()

    yield

    # Shutdown infrastructure — run all teardowns concurrently with a hard
    # timeout so that a single hung driver cannot freeze the entire process
    # (critical for uvicorn --reload).
    async def _safe_close(name: str, coro) -> None:
        try:
            await asyncio.wait_for(coro, timeout=_SHUTDOWN_TIMEOUT)
        except TimeoutError:
            logger.warning(
                "Shutdown: %s close timed out after %.0fs — skipping", name, _SHUTDOWN_TIMEOUT
            )
        except Exception as e:
            logger.warning("Shutdown: %s close failed: %s", name, e)

    await asyncio.gather(
        _safe_close("database", close_db()),
        _safe_close("neo4j", neo4j_client.close()),
        _safe_close("redis", redis_client.close()),
    )
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
    # SecurityHeaders must be outermost (added last) so it runs on ALL
    # responses, including CORS preflight responses generated by CORSMiddleware.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    # Health check endpoint with quick Redis ping
    @app.get(f"{settings.api_prefix}/health")
    async def health_check() -> dict[str, Any]:
        """Health check endpoint for monitoring and load balancers.

        Performs a fast Redis ping to detect degraded state.
        """
        status = "healthy"
        try:
            pong = await redis_client.client.ping()
            if not pong:
                status = "degraded"
        except Exception:
            status = "degraded"

        return {
            "status": status,
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
            neo4j_status.get("status") == "healthy" and redis_status.get("status") == "healthy"
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

    # Global exception handler -- catches anything domains don't handle
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        detail = "Internal server error"
        if settings.debug:
            detail = f"{type(exc).__name__}: {exc}"
        return JSONResponse(
            status_code=500,
            content={"detail": detail},
        )

    # Domain routers
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(oauth_router, prefix=settings.api_prefix)
    app.include_router(documents_router, prefix=settings.api_prefix)
    app.include_router(knowledge_router, prefix=settings.api_prefix)
    app.include_router(agents_router, prefix=settings.api_prefix)
    app.include_router(ingestion_router, prefix=settings.api_prefix)
    app.include_router(settings_router, prefix=settings.api_prefix)

    return app


app = create_app()
