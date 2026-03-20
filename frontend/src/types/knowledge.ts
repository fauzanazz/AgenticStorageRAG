/**
 * Knowledge graph types matching backend schemas.
 */

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

export interface GraphCluster {
  id: string;
  label: string;
  parent_id: string | null;
  node_ids: string[];
  description: string | null;
}

export interface GraphVisualization {
  nodes: GraphNode[];
  edges: GraphEdge[];
  clusters?: GraphCluster[];
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
