"""Import JSONL seed files into Neo4j + PostgreSQL shadow tables.

Reads manifest.json to discover files, applies schema, then batch-imports
entities and relationships into both Neo4j and PostgreSQL.

Run:  python -m app.scripts.graph_import
      python -m app.scripts.graph_import --clean   (wipe and re-import)
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neo4j import AsyncGraphDatabase

from app.config import get_settings
from app.scripts.graph_schema import apply_schema

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Graph seed directory relative to backend/
SEED_DIR = Path(__file__).resolve().parent.parent.parent / "graph_seed"
MANIFEST_PATH = SEED_DIR / "manifest.json"

# Batch size for UNWIND operations
BATCH_SIZE = 500


def _read_manifest() -> dict[str, Any]:
    """Read and validate the manifest file."""
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Manifest not found: {MANIFEST_PATH}")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    logger.info(
        "Manifest: version=%s, updated_at=%s, entities=%d, relationships=%d",
        manifest.get("version"),
        manifest.get("updated_at"),
        manifest.get("stats", {}).get("total_entities", 0),
        manifest.get("stats", {}).get("total_relationships", 0),
    )
    return manifest


def _verify_checksum(manifest: dict[str, Any]) -> bool:
    """Verify the manifest checksum against actual file contents."""
    expected = manifest.get("checksum", "")
    if not expected:
        logger.warning("No checksum in manifest, skipping verification")
        return True

    hasher = hashlib.sha256()
    files = manifest.get("files", {})
    all_data_files = sorted(
        files.get("entities", []) + files.get("relationships", [])
    )

    for rel_path in all_data_files:
        full_path = SEED_DIR / rel_path
        if full_path.exists():
            hasher.update(full_path.read_bytes())
        else:
            logger.warning("Missing data file: %s", rel_path)

    actual = f"sha256:{hasher.hexdigest()}"
    if actual != expected:
        logger.warning("Checksum mismatch! Expected: %s, Got: %s", expected, actual)
        return False

    logger.info("Checksum verified: %s", actual[:30] + "...")
    return True


def _read_jsonl_files(file_paths: list[str]) -> list[dict[str, Any]]:
    """Read records from one or more JSONL files."""
    records: list[dict[str, Any]] = []
    for rel_path in file_paths:
        full_path = SEED_DIR / rel_path
        if not full_path.exists():
            logger.warning("Skipping missing file: %s", rel_path)
            continue

        with open(full_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.warning("Bad JSON at %s:%d: %s", rel_path, line_num, e)

    return records


def _sanitize_label(label: str) -> str:
    """Sanitize a Neo4j label to prevent injection."""
    return "".join(c for c in label if c.isalnum() or c == "_")


async def _clean_graph(driver: Any, database: str) -> None:
    """Delete all nodes and relationships from Neo4j."""
    logger.info("Cleaning Neo4j graph (batched DETACH DELETE)...")
    async with driver.session(database=database) as session:
        # Delete in batches to avoid memory issues
        deleted_total = 0
        while True:
            result = await session.run(
                """
                MATCH (n)
                WITH n LIMIT 5000
                DETACH DELETE n
                RETURN count(*) AS deleted
                """
            )
            record = await result.single()
            deleted = record["deleted"] if record else 0
            deleted_total += deleted
            if deleted == 0:
                break

    logger.info("Deleted %d nodes from Neo4j", deleted_total)


async def _clean_pg_shadow() -> None:
    """Truncate PostgreSQL shadow tables for knowledge entities and relationships."""
    from app.infra.database import init_db, close_db

    logger.info("Cleaning PostgreSQL shadow tables...")
    engine, session_factory = init_db()

    async with session_factory() as session:
        # Delete relationships first (FK dependency), then entities
        await session.execute(
            __import__("sqlalchemy").text("DELETE FROM knowledge_relationships")
        )
        await session.execute(
            __import__("sqlalchemy").text("DELETE FROM knowledge_entities")
        )
        await session.commit()

    await close_db()
    logger.info("PostgreSQL shadow tables cleaned")


async def _import_entities_neo4j(
    driver: Any,
    database: str,
    entities: list[dict[str, Any]],
) -> int:
    """Batch-import entities into Neo4j using UNWIND + MERGE.

    Each entity gets:
    - Its type-specific label (e.g., :Person)
    - A universal :Entity label (for shared indexes)
    """
    if not entities:
        return 0

    imported = 0
    # Group by entity_type for label-specific MERGE
    by_type: dict[str, list[dict[str, Any]]] = {}
    for ent in entities:
        etype = ent.get("entity_type", "Unknown")
        by_type.setdefault(etype, []).append(ent)

    for entity_type, type_entities in by_type.items():
        label = _sanitize_label(entity_type)

        # Process in batches
        for i in range(0, len(type_entities), BATCH_SIZE):
            batch = type_entities[i : i + BATCH_SIZE]

            # Prepare batch data
            batch_data = []
            for ent in batch:
                props: dict[str, Any] = {
                    "neo4j_id": ent["neo4j_id"],
                    "name": ent["name"],
                    "entity_type": entity_type,
                }
                if ent.get("description"):
                    props["description"] = ent["description"]
                if ent.get("properties"):
                    props["properties_json"] = json.dumps(ent["properties"])
                batch_data.append(props)

            async with driver.session(database=database) as session:
                await session.run(
                    f"""
                    UNWIND $batch AS props
                    MERGE (n:Entity {{neo4j_id: props.neo4j_id}})
                    SET n:{label},
                        n.name = props.name,
                        n.entity_type = props.entity_type,
                        n.description = props.description,
                        n.properties_json = props.properties_json
                    """,
                    {"batch": batch_data},
                )

            imported += len(batch)

    logger.info("Imported %d entities into Neo4j", imported)
    return imported


async def _import_relationships_neo4j(
    driver: Any,
    database: str,
    relationships: list[dict[str, Any]],
) -> int:
    """Batch-import relationships into Neo4j using UNWIND + MERGE."""
    if not relationships:
        return 0

    imported = 0
    # Group by relationship_type for type-specific creation
    by_type: dict[str, list[dict[str, Any]]] = {}
    for rel in relationships:
        rtype = rel.get("relationship_type", "RELATED_TO")
        by_type.setdefault(rtype, []).append(rel)

    for rel_type, type_rels in by_type.items():
        label = _sanitize_label(rel_type)

        for i in range(0, len(type_rels), BATCH_SIZE):
            batch = type_rels[i : i + BATCH_SIZE]

            batch_data = []
            for rel in batch:
                props: dict[str, Any] = {
                    "neo4j_id": rel.get("neo4j_id", str(uuid.uuid4())),
                    "weight": rel.get("weight", 1.0),
                    "source_neo4j_id": rel["source_neo4j_id"],
                    "target_neo4j_id": rel["target_neo4j_id"],
                }
                if rel.get("properties"):
                    props["properties_json"] = json.dumps(rel["properties"])
                batch_data.append(props)

            async with driver.session(database=database) as session:
                await session.run(
                    f"""
                    UNWIND $batch AS props
                    MATCH (a:Entity {{neo4j_id: props.source_neo4j_id}})
                    MATCH (b:Entity {{neo4j_id: props.target_neo4j_id}})
                    MERGE (a)-[r:{label} {{neo4j_id: props.neo4j_id}}]->(b)
                    SET r.weight = props.weight,
                        r.properties_json = props.properties_json
                    """,
                    {"batch": batch_data},
                )

            imported += len(batch)

    logger.info("Imported %d relationships into Neo4j", imported)
    return imported


async def _import_pg_shadow(
    entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
) -> dict[str, int]:
    """Import entities and relationships into PostgreSQL shadow tables.

    Uses the same data format as the JSONL files. Creates KnowledgeEntity
    and KnowledgeRelationship records, matching Neo4j by neo4j_id.
    """
    from sqlalchemy import select

    from app.domain.knowledge.models import KnowledgeEntity, KnowledgeRelationship
    from app.infra.database import init_db, close_db

    engine, session_factory = init_db()
    entity_count = 0
    rel_count = 0

    async with session_factory() as session:
        # --- Import entities ---
        # Build set of existing neo4j_ids for skip logic
        existing_result = await session.execute(
            select(KnowledgeEntity.neo4j_id)
        )
        existing_ids = {row[0] for row in existing_result.all()}

        neo4j_id_to_pg_id: dict[str, uuid.UUID] = {}

        # Map existing entities
        if existing_ids:
            existing_entities = await session.execute(
                select(KnowledgeEntity.neo4j_id, KnowledgeEntity.id)
            )
            for neo_id, pg_id in existing_entities.all():
                neo4j_id_to_pg_id[neo_id] = pg_id

        for ent in entities:
            neo_id = ent["neo4j_id"]
            if neo_id in existing_ids:
                continue  # Already exists, skip (idempotent)

            pg_id = uuid.uuid4()
            db_entity = KnowledgeEntity(
                id=pg_id,
                neo4j_id=neo_id,
                entity_type=ent["entity_type"],
                name=ent["name"],
                description=ent.get("description"),
                properties_json=json.dumps(ent["properties"]) if ent.get("properties") else None,
                source_document_id=None,  # Seed data has no document association
            )
            session.add(db_entity)
            neo4j_id_to_pg_id[neo_id] = pg_id
            entity_count += 1

        await session.flush()

        # --- Import relationships ---
        existing_rel_result = await session.execute(
            select(KnowledgeRelationship.neo4j_id)
        )
        existing_rel_ids = {row[0] for row in existing_rel_result.all()}

        for rel in relationships:
            neo_id = rel.get("neo4j_id", str(uuid.uuid4()))
            if neo_id in existing_rel_ids:
                continue  # Already exists, skip

            source_pg_id = neo4j_id_to_pg_id.get(rel["source_neo4j_id"])
            target_pg_id = neo4j_id_to_pg_id.get(rel["target_neo4j_id"])

            if not source_pg_id or not target_pg_id:
                logger.debug(
                    "Skipping relationship %s: missing entity mapping (source=%s, target=%s)",
                    neo_id,
                    rel["source_neo4j_id"],
                    rel["target_neo4j_id"],
                )
                continue

            db_rel = KnowledgeRelationship(
                neo4j_id=neo_id,
                relationship_type=rel["relationship_type"],
                source_entity_id=source_pg_id,
                target_entity_id=target_pg_id,
                properties_json=json.dumps(rel["properties"]) if rel.get("properties") else None,
                weight=rel.get("weight", 1.0),
                source_document_id=None,
            )
            session.add(db_rel)
            rel_count += 1

        await session.commit()

    await close_db()

    logger.info("PG shadow: %d entities, %d relationships imported", entity_count, rel_count)
    return {"entities": entity_count, "relationships": rel_count}


async def import_graph(clean: bool = False) -> dict[str, Any]:
    """Import graph seed files into Neo4j and PostgreSQL.

    Args:
        clean: If True, wipe existing graph before importing.

    Returns:
        Dict with import stats.
    """
    settings = get_settings()

    # Read manifest
    manifest = _read_manifest()

    # Verify checksum (warn only, don't abort)
    _verify_checksum(manifest)

    files = manifest.get("files", {})
    entity_files = files.get("entities", [])
    rel_files = files.get("relationships", [])

    # Check if there's anything to import
    if not entity_files and not rel_files:
        logger.info("No data files in manifest, applying schema only")

    # Read all data
    entities = _read_jsonl_files(entity_files)
    relationships = _read_jsonl_files(rel_files)

    logger.info("Read %d entities, %d relationships from seed files", len(entities), len(relationships))

    # Connect to Neo4j
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    try:
        await driver.verify_connectivity()

        # Clean if requested
        if clean:
            await _clean_graph(driver, settings.neo4j_database)
            await _clean_pg_shadow()

        # Apply schema (always, idempotent)
        schema_result = await apply_schema(driver, settings.neo4j_database)

        # Import into Neo4j
        neo4j_entities = await _import_entities_neo4j(
            driver, settings.neo4j_database, entities
        )
        neo4j_rels = await _import_relationships_neo4j(
            driver, settings.neo4j_database, relationships
        )

    finally:
        await driver.close()

    # Import into PostgreSQL shadow tables
    pg_result = await _import_pg_shadow(entities, relationships)

    result = {
        "manifest_version": manifest.get("version"),
        "clean_import": clean,
        "schema": schema_result,
        "neo4j": {"entities": neo4j_entities, "relationships": neo4j_rels},
        "postgresql": pg_result,
    }

    logger.info("Import complete: %s", json.dumps(result, indent=2))
    return result


async def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Import graph seed files into Neo4j + PostgreSQL"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Wipe existing graph before importing",
    )
    args = parser.parse_args()

    await import_graph(clean=args.clean)


if __name__ == "__main__":
    asyncio.run(main())
