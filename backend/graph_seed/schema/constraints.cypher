-- Neo4j Schema Initialization for DingDong RAG
-- Idempotent: safe to run on every startup (uses IF NOT EXISTS)
--
-- All knowledge graph entities get a secondary :Entity label in addition
-- to their type-specific label (e.g., :Person, :Organization).
-- This enables universal indexes on shared properties.

-- ============================================================
-- Uniqueness Constraints (also create implicit indexes)
-- ============================================================

-- Every node must have a unique neo4j_id (UUID generated application-side)
CREATE CONSTRAINT entity_neo4j_id IF NOT EXISTS
FOR (n:Entity) REQUIRE n.neo4j_id IS UNIQUE;

-- ============================================================
-- Property Indexes (for fast lookups)
-- ============================================================

-- Index on name for CONTAINS-based search queries
CREATE INDEX entity_name IF NOT EXISTS
FOR (n:Entity) ON (n.name);

-- Index on entity_type for filtered queries
CREATE INDEX entity_type IF NOT EXISTS
FOR (n:Entity) ON (n.entity_type);

-- ============================================================
-- Relationship Property Indexes
-- ============================================================

-- Index on relationship neo4j_id for cross-referencing with PG
CREATE INDEX rel_neo4j_id IF NOT EXISTS
FOR ()-[r:RELATED_TO]-() ON (r.neo4j_id);

-- ============================================================
-- Full-Text Search Index (APOC / Neo4j native)
-- ============================================================

-- Full-text index on name + description for natural language search
CREATE FULLTEXT INDEX entity_fulltext_search IF NOT EXISTS
FOR (n:Entity) ON EACH [n.name, n.description];
