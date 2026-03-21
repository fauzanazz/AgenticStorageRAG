"""Neo4j driver wrapper.

Provides connection pool, health check, and typed query helpers
for the Knowledge Graph. Uses a SEPARATE database from other projects.
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j import AsyncSession as Neo4jAsyncSession

from app.config import get_settings

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Async Neo4j client with connection pooling and health checks.

    This client is initialized once during app startup and shared
    across all requests via dependency injection.
    """

    def __init__(self) -> None:
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        """Initialize the Neo4j driver connection pool."""
        settings = get_settings()
        self._driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_pool_size=50,
            connection_acquisition_timeout=30,
        )
        # Verify connectivity
        await self._driver.verify_connectivity()
        logger.info(
            "Neo4j connected: %s (database: %s)",
            settings.neo4j_uri,
            settings.neo4j_database,
        )

    async def close(self) -> None:
        """Close the Neo4j driver and release connections."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")

    @property
    def driver(self) -> AsyncDriver:
        """Get the Neo4j driver, raising if not connected."""
        if self._driver is None:
            raise RuntimeError("Neo4j not connected. Call connect() first.")
        return self._driver

    def _get_database(self) -> str:
        """Get the configured database name (separate from other projects)."""
        return get_settings().neo4j_database

    async def health_check(self) -> dict[str, Any]:
        """Check Neo4j connectivity and return status info."""
        try:
            async with self.driver.session(database=self._get_database()) as session:
                result = await session.run("RETURN 1 AS healthy")
                record = await result.single()
                return {
                    "status": "healthy" if record and record["healthy"] == 1 else "unhealthy",
                    "database": self._get_database(),
                }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a read query and return results as list of dicts."""
        async with self.driver.session(database=self._get_database()) as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            return records

    async def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a write query and return results as list of dicts."""

        async def _tx_func(tx: Any, q: str, p: dict[str, Any]) -> list[dict[str, Any]]:
            result = await tx.run(q, p)
            return await result.data()

        async with self.driver.session(database=self._get_database()) as session:
            return await session.execute_write(_tx_func, query, parameters or {})

    async def execute_write_batch(
        self,
        queries: list[tuple[str, dict[str, Any]]],
    ) -> None:
        """Execute multiple write queries in a single transaction."""

        async def _tx_func(tx: Any, qs: list[tuple[str, dict[str, Any]]]) -> None:
            for query, params in qs:
                await tx.run(query, params)

        async with self.driver.session(database=self._get_database()) as session:
            await session.execute_write(_tx_func, queries)

    async def get_session(self) -> Neo4jAsyncSession:
        """Get a raw Neo4j session for advanced use cases."""
        return self.driver.session(database=self._get_database())


# Module-level singleton (initialized via lifespan)
neo4j_client = Neo4jClient()
