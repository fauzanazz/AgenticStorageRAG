"use client";

import { useState, useCallback } from "react";
import { apiClient } from "@/lib/api-client";
import type {
  GraphVisualization,
  KnowledgeStats,
  HybridSearchResult,
} from "@/types/knowledge";

export function useKnowledge() {
  const [graph, setGraph] = useState<GraphVisualization | null>(null);
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [searchResults, setSearchResults] = useState<HybridSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchGraph = useCallback(
    async (params?: {
      document_id?: string;
      entity_types?: string;
      limit?: number;
    }) => {
      setLoading(true);
      setError(null);
      try {
        const queryParams = new URLSearchParams();
        if (params?.document_id) queryParams.set("document_id", params.document_id);
        if (params?.entity_types) queryParams.set("entity_types", params.entity_types);
        if (params?.limit) queryParams.set("limit", String(params.limit));

        const qs = queryParams.toString();
        const url = `/knowledge/graph${qs ? `?${qs}` : ""}`;
        const data = await apiClient.get<GraphVisualization>(url);
        setGraph(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch graph");
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const fetchStats = useCallback(async () => {
    try {
      const data = await apiClient.get<KnowledgeStats>("/knowledge/stats");
      setStats(data);
    } catch (err) {
      console.error("Failed to fetch stats:", err);
    }
  }, []);

  const search = useCallback(
    async (query: string, vectorWeight: number = 0.5) => {
      setLoading(true);
      setError(null);
      try {
        const data = await apiClient.post<HybridSearchResult[]>(
          "/knowledge/search/hybrid",
          {
            query,
            vector_weight: vectorWeight,
            top_k: 20,
          }
        );
        setSearchResults(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Search failed");
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return {
    graph,
    stats,
    searchResults,
    loading,
    error,
    fetchGraph,
    fetchStats,
    search,
  };
}
