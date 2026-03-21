"""Export Neo4j knowledge graph to versioned JSONL seed files.

Reads all entities and relationships from Neo4j, shards them by type
into JSONL files, and updates the manifest with version metadata.

Run:  python -m app.scripts.graph_export
      python -m app.scripts.graph_export --shard-size 40  (MB threshold per file)
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from neo4j import AsyncGraphDatabase

from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Graph seed directory relative to backend/
SEED_DIR = Path(__file__).resolve().parent.parent.parent / "graph_seed"
ENTITIES_DIR = SEED_DIR / "entities"
RELATIONSHIPS_DIR = SEED_DIR / "relationships"
MANIFEST_PATH = SEED_DIR / "manifest.json"

# Default max file size before sharding (in MB)
DEFAULT_SHARD_SIZE_MB = 40


def _sanitize_filename(name: str) -> str:
    """Sanitize a type name for use as a filename."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in name)


def _write_sharded_jsonl(
    records: list[dict[str, Any]],
    output_dir: Path,
    type_name: str,
    max_size_mb: int,
) -> list[str]:
    """Write records to JSONL files, sharding if file exceeds max_size_mb.

    Returns list of relative file paths (relative to SEED_DIR).
    """
    if not records:
        return []

    safe_name = _sanitize_filename(type_name)
    max_bytes = max_size_mb * 1024 * 1024
    output_dir.mkdir(parents=True, exist_ok=True)

    files_written: list[str] = []
    current_shard = 1
    current_size = 0
    current_file: Any = None
    current_path: Path | None = None

    def _open_shard() -> tuple[Any, Path]:
        nonlocal current_shard
        if len(records) <= _estimate_records_per_shard(records, max_bytes):
            # Single file, no shard suffix
            path = output_dir / f"{safe_name}.jsonl"
        else:
            path = output_dir / f"{safe_name}_{current_shard:03d}.jsonl"
        current_shard += 1
        return open(path, "w", encoding="utf-8"), path

    def _estimate_records_per_shard(recs: list[dict], max_b: int) -> int:
        """Estimate how many records fit in one shard."""
        if not recs:
            return 0
        sample = json.dumps(recs[0], ensure_ascii=False)
        avg_line_size = len(sample.encode("utf-8")) + 1  # +1 for newline
        if avg_line_size == 0:
            return len(recs)
        return max(1, max_b // avg_line_size)

    try:
        current_file, current_path = _open_shard()

        for record in records:
            line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
            line_bytes = len(line.encode("utf-8"))

            # Check if we need a new shard
            if current_size + line_bytes > max_bytes and current_size > 0:
                current_file.close()
                rel_path = str(current_path.relative_to(SEED_DIR))
                files_written.append(rel_path)

                current_size = 0
                current_file, current_path = _open_shard()

            current_file.write(line)
            current_size += line_bytes

        current_file.close()
        if current_path:
            rel_path = str(current_path.relative_to(SEED_DIR))
            files_written.append(rel_path)

    except Exception:
        if current_file and not current_file.closed:
            current_file.close()
        raise

    return files_written


def _compute_checksum(seed_dir: Path, entity_files: list[str], rel_files: list[str]) -> str:
    """Compute SHA-256 checksum over all data files."""
    hasher = hashlib.sha256()

    for rel_path in sorted(entity_files + rel_files):
        full_path = seed_dir / rel_path
        if full_path.exists():
            hasher.update(full_path.read_bytes())

    return f"sha256:{hasher.hexdigest()}"


async def export_graph(shard_size_mb: int = DEFAULT_SHARD_SIZE_MB) -> dict[str, Any]:
    """Export the full Neo4j knowledge graph to JSONL seed files.

    Returns:
        Dict with export stats and manifest info.
    """
    settings = get_settings()

    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    try:
        await driver.verify_connectivity()
        logger.info("Connected to Neo4j: %s", settings.neo4j_uri)

        # --- Export entities ---
        async with driver.session(database=settings.neo4j_database) as session:
            result = await session.run(
                """
                MATCH (n:Entity)
                RETURN n.neo4j_id AS neo4j_id,
                       n.name AS name,
                       n.entity_type AS entity_type,
                       n.description AS description,
                       n.properties_json AS properties_json,
                       labels(n) AS labels
                ORDER BY n.entity_type, n.name
                """
            )
            all_entities = await result.data()

        # Group entities by type
        entities_by_type: dict[str, list[dict[str, Any]]] = {}
        for record in all_entities:
            entity_type = record.get("entity_type", "Unknown")
            props = None
            if record.get("properties_json"):
                try:
                    props = json.loads(record["properties_json"])
                except (json.JSONDecodeError, TypeError):
                    props = None

            entity_data = {
                "neo4j_id": record["neo4j_id"],
                "name": record["name"],
                "entity_type": entity_type,
                "description": record.get("description"),
                "properties": props,
            }

            entities_by_type.setdefault(entity_type, []).append(entity_data)

        # --- Export relationships ---
        async with driver.session(database=settings.neo4j_database) as session:
            result = await session.run(
                """
                MATCH (a:Entity)-[r]->(b:Entity)
                RETURN r.neo4j_id AS neo4j_id,
                       type(r) AS relationship_type,
                       a.neo4j_id AS source_neo4j_id,
                       b.neo4j_id AS target_neo4j_id,
                       r.weight AS weight,
                       r.properties_json AS properties_json
                ORDER BY type(r), a.name
                """
            )
            all_relationships = await result.data()

        # Group relationships by type
        rels_by_type: dict[str, list[dict[str, Any]]] = {}
        for record in all_relationships:
            rel_type = record.get("relationship_type", "RELATED_TO")
            props = None
            if record.get("properties_json"):
                try:
                    props = json.loads(record["properties_json"])
                except (json.JSONDecodeError, TypeError):
                    props = None

            rel_data = {
                "neo4j_id": record["neo4j_id"],
                "relationship_type": rel_type,
                "source_neo4j_id": record["source_neo4j_id"],
                "target_neo4j_id": record["target_neo4j_id"],
                "weight": record.get("weight", 1.0),
                "properties": props,
            }

            rels_by_type.setdefault(rel_type, []).append(rel_data)

        # --- Clean old files ---
        for f in ENTITIES_DIR.glob("*.jsonl"):
            f.unlink()
        for f in RELATIONSHIPS_DIR.glob("*.jsonl"):
            f.unlink()

        # --- Write entity files ---
        entity_files: list[str] = []
        entity_type_counts: dict[str, int] = {}
        for entity_type, entities in sorted(entities_by_type.items()):
            files = _write_sharded_jsonl(entities, ENTITIES_DIR, entity_type, shard_size_mb)
            entity_files.extend(files)
            entity_type_counts[entity_type] = len(entities)

        # --- Write relationship files ---
        rel_files: list[str] = []
        rel_type_counts: dict[str, int] = {}
        for rel_type, rels in sorted(rels_by_type.items()):
            files = _write_sharded_jsonl(rels, RELATIONSHIPS_DIR, rel_type, shard_size_mb)
            rel_files.extend(files)
            rel_type_counts[rel_type] = len(rels)

        # --- Compute checksum ---
        checksum = _compute_checksum(SEED_DIR, entity_files, rel_files)

        # --- Update manifest ---
        total_entities = sum(entity_type_counts.values())
        total_relationships = sum(rel_type_counts.values())

        manifest = {
            "version": _bump_version(),
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by": "graph_export",
            "description": f"Exported {total_entities} entities, {total_relationships} relationships",
            "source": "neo4j_export",
            "stats": {
                "total_entities": total_entities,
                "total_relationships": total_relationships,
                "entity_types": entity_type_counts,
                "relationship_types": rel_type_counts,
            },
            "files": {
                "entities": sorted(entity_files),
                "relationships": sorted(rel_files),
                "schema": ["schema/constraints.cypher"],
            },
            "checksum": checksum,
        }

        MANIFEST_PATH.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        logger.info(
            "Export complete: %d entities (%d types), %d relationships (%d types)",
            total_entities,
            len(entity_type_counts),
            total_relationships,
            len(rel_type_counts),
        )
        logger.info("Manifest updated: %s", MANIFEST_PATH)
        logger.info("Checksum: %s", checksum)

        # Report file sizes
        for rel_path in entity_files + rel_files:
            full = SEED_DIR / rel_path
            size_mb = full.stat().st_size / (1024 * 1024)
            if size_mb > 1:
                logger.info("  %s: %.1f MB", rel_path, size_mb)

        return manifest

    finally:
        await driver.close()


def _bump_version() -> str:
    """Read current manifest version and bump patch number."""
    if MANIFEST_PATH.exists():
        try:
            current = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            version = current.get("version", "1.0.0")
            parts = version.split(".")
            if len(parts) == 3:
                parts[2] = str(int(parts[2]) + 1)
                return ".".join(parts)
        except (json.JSONDecodeError, ValueError, IndexError):
            pass
    return "1.0.0"


async def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Export Neo4j graph to JSONL seed files")
    parser.add_argument(
        "--shard-size",
        type=int,
        default=DEFAULT_SHARD_SIZE_MB,
        help=f"Max file size in MB before sharding (default: {DEFAULT_SHARD_SIZE_MB})",
    )
    args = parser.parse_args()

    await export_graph(shard_size_mb=args.shard_size)


if __name__ == "__main__":
    asyncio.run(main())
