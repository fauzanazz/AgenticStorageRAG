"""Alembic environment configuration.

Wired to use the app's SQLAlchemy Base metadata and database URL
from the application config.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.infra.database import Base

# Import all domain models here so Alembic can detect them
from app.domain.auth.models import *  # noqa: F401, F403
from app.domain.documents.models import *  # noqa: F401, F403
from app.domain.knowledge.models import *  # noqa: F401, F403
from app.domain.agents.models import *  # noqa: F401, F403
from app.domain.ingestion.models import *  # noqa: F401, F403
from app.domain.settings.models import *  # noqa: F401, F403

# Alembic Config object
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the target metadata for autogenerate
target_metadata = Base.metadata

# Prefer MIGRATIONS_URL (sync, direct connection) over DATABASE_URL (async, pooler)
settings = get_settings()
_migrations_url = os.environ.get("MIGRATIONS_URL")
_database_url = settings.database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL script without connecting to the database.
    """
    url = _migrations_url or _database_url
    # Offline mode uses sync driver -- strip asyncpg
    url = url.replace("+asyncpg", "")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    """Run migrations with the given connection."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online_sync() -> None:
    """Run migrations using a sync engine (for MIGRATIONS_URL)."""
    connectable = create_engine(
        _migrations_url,  # type: ignore[arg-type]
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        connection.execute(connection.default_isolation_level)  # noqa
        do_run_migrations(connection)

    connectable.dispose()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        # Supabase uses pgbouncer in transaction mode, which doesn't support
        # prepared statements. Disable asyncpg's statement cache.
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
            "server_settings": {"statement_timeout": "120000"},  # 120s for DDL
        },
    )

    async with connectable.connect() as connection:
        # Override Supabase's default statement timeout for DDL migrations
        await connection.exec_driver_sql("SET statement_timeout = '120s'")
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Uses sync engine with MIGRATIONS_URL (direct connection) if available,
    otherwise falls back to async engine with DATABASE_URL (pooler).
    """
    import asyncio
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
