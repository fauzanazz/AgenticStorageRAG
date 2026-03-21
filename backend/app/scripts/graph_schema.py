"""Neo4j schema initialization.

Applies indexes and constraints from the schema/constraints.cypher file.
Idempotent: all statements use IF NOT EXISTS, safe to run on every startup.

Run standalone:  python -m app.scripts.graph_schema
Called from:     graph_import.py, main.py lifespan
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from neo4j import AsyncDriver

from app.config import get_settings

logger = logging.getLogger(__name__)

# Resolve path relative to backend/ directory
SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "graph_seed" / "schema"
CONSTRAINTS_FILE = SCHEMA_DIR / "constraints.cypher"


def _parse_cypher_statements(file_path: Path) -> list[str]:
    """Parse a .cypher file into individual statements.

    Strips comments (lines starting with --) and splits on semicolons.
    """
    if not file_path.exists():
        logger.warning("Schema file not found: %s", file_path)
        return []

    content = file_path.read_text(encoding="utf-8")
    statements: list[str] = []

    for raw_stmt in content.split(";"):
        # Remove comment lines and blank lines
        lines = []
        for line in raw_stmt.strip().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("--"):
                lines.append(line)
        stmt = "\n".join(lines).strip()
        if stmt:
            statements.append(stmt)

    return statements


async def apply_schema(driver: AsyncDriver, database: str | None = None) -> dict[str, Any]:
    """Apply Neo4j schema from constraints.cypher.

    Args:
        driver: Connected Neo4j async driver
        database: Target database name (uses settings default if None)

    Returns:
        Dict with applied count and any errors
    """
    if database is None:
        database = get_settings().neo4j_database

    statements = _parse_cypher_statements(CONSTRAINTS_FILE)
    if not statements:
        logger.info("No schema statements to apply")
        return {"applied": 0, "errors": []}

    applied = 0
    errors: list[str] = []

    async with driver.session(database=database) as session:
        for stmt in statements:
            try:
                await session.run(stmt)
                applied += 1
                # Log first 80 chars of statement for visibility
                preview = stmt.replace("\n", " ")[:80]
                logger.debug("Applied schema: %s...", preview)
            except Exception as e:
                error_msg = f"Schema statement failed: {e}"
                logger.warning(error_msg)
                errors.append(error_msg)

    logger.info(
        "Neo4j schema: %d statements applied, %d errors",
        applied,
        len(errors),
    )
    return {"applied": applied, "errors": errors}


async def main() -> None:
    """Standalone entry point for schema initialization."""

    from neo4j import AsyncGraphDatabase

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    settings = get_settings()
    logger.info("Applying Neo4j schema to %s (%s)", settings.neo4j_uri, settings.neo4j_database)

    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    try:
        await driver.verify_connectivity()
        result = await apply_schema(driver, settings.neo4j_database)
        logger.info("Schema result: %s", result)
    finally:
        await driver.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
