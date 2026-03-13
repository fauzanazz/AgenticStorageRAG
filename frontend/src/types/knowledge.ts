/**
 * Knowledge graph types matching backend schemas.
 */

export interface KnowledgeEntity {
  id: string;
  neo4j_id: string;
  entity_type: string;
  name: string;
  description: string | null;
  properties: Record<string, unknown> | null;
  source_document_id: string | null;
  created_at: string;
  updated_at: string;
  relationship_count: number;
}

export interface KnowledgeRelationship {
  id: string;
  neo4j_id: string;
  relationship_type: string;
  source_entity_id: string;
  target_entity_id: string;
  source_entity_name: string | null;
  target_entity_name: string | null;
  properties: Record<string, unknown> | null;
  weight: number;
  source_document_id: string | null;
  created_at: string;
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  description: string | null;
  properties: Record<string, unknown> | null;
  size: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  label: string;
  weight: number;
}

export interface GraphVisualization {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
}

export interface KnowledgeStats {
  total_entities: number;
  total_relationships: number;
  total_embeddings: number;
  entity_types: Record<string, number>;
  relationship_types: Record<string, number>;
}

export interface HybridSearchResult {
  content: string;
  source: "vector" | "graph" | "both";
  score: number;
  document_id: string | null;
  chunk_id: string | null;
  entity_id: string | null;
  metadata: Record<string, unknown> | null;
}
