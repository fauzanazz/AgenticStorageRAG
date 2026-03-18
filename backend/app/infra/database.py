"""Database engine and session management.

Provides async SQLAlchemy engine and session factory for Supabase PostgreSQL.
In local development, connects to the Docker Compose PostgreSQL instance.
In production, connects to Supabase PostgreSQL.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models.

    All domain models inherit from this. Provides:
    - Common table args (if needed)
    - Centralized metadata for Alembic
    """

    pass


def create_engine() -> "AsyncEngine":  # noqa: F821
    """Create the async SQLAlchemy engine from settings."""
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        # Supabase uses pgbouncer in transaction mode, which doesn't support
        # prepared statements. Disable asyncpg's statement cache.
        connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0},
    )
    return engine


def create_session_factory(engine: "AsyncEngine") -> async_sessionmaker[AsyncSession]:  # noqa: F821
    """Create a session factory bound to the given engine."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


# Module-level defaults (initialized lazily via lifespan)
_engine: "AsyncEngine | None" = None  # noqa: F821
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db() -> tuple["AsyncEngine", async_sessionmaker[AsyncSession]]:  # noqa: F821
    """Initialize the database engine and session factory.

    Called during application startup (lifespan).
    Returns the engine and session factory for DI registration.
    """
    global _engine, _session_factory
    _engine = create_engine()
    _session_factory = create_session_factory(_engine)
    return _engine, _session_factory


def build_session_factory(
    url: "URL | str",  # noqa: F821
) -> tuple["AsyncEngine", async_sessionmaker[AsyncSession]]:  # noqa: F821
    """Create a fresh engine + session factory bound to the current event loop.

    Use this inside Celery tasks (asyncio.run) so the engine is bound to the
    task's event loop, not the API server's event loop.  Always call
    ``await engine.dispose()`` in a finally block after the task finishes.

    Args:
        url: SQLAlchemy database URL (use ``_engine.url`` from the global engine).

    Returns:
        Tuple of (engine, session_factory) scoped to the current event loop.
    """
    from sqlalchemy.engine import URL as SAUrl  # noqa: F811

    engine = create_async_engine(
        url if isinstance(url, str) else url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0},
    )
    session_factory = create_session_factory(engine)
    return engine, session_factory


async def close_db() -> None:
    """Close the database engine. Called during application shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session for dependency injection.

    Usage in FastAPI:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db_session)):
            ...
    """
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
