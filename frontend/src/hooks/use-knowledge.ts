"use client";

import {
  useQuery,
  useMutation,
  useQueryClient,
  keepPreviousData,
} from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type {
  GraphVisualization,
  KnowledgeStats,
  HybridSearchResult,
} from "@/types/knowledge";

// ── Query / mutation functions ─────────────────────────────────────────────

function fetchGraph(params?: {
  document_id?: string;
  entity_types?: string;
  limit?: number;
}): Promise<GraphVisualization> {
  const qs = new URLSearchParams();
  if (params?.document_id) qs.set("document_id", params.document_id);
  if (params?.entity_types) qs.set("entity_types", params.entity_types);
  if (params?.limit) qs.set("limit", String(params.limit));
  const query = qs.toString();
  return apiClient.get<GraphVisualization>(
    `/knowledge/graph${query ? `?${query}` : ""}`
  );
}

function fetchStats(): Promise<KnowledgeStats> {
  return apiClient.get<KnowledgeStats>("/knowledge/stats");
}

function hybridSearch(
  query: string,
  vectorWeight: number,
  topK: number
): Promise<HybridSearchResult[]> {
  return apiClient.post<HybridSearchResult[]>("/knowledge/search/hybrid", {
    query,
    vector_weight: vectorWeight,
    top_k: topK,
  });
}

// ── Hook ───────────────────────────────────────────────────────────────────

interface UseKnowledgeOptions {
  graphParams?: {
    document_id?: string;
    entity_types?: string;
    limit?: number;
  };
}

export function useKnowledge(options: UseKnowledgeOptions = {}) {
  const queryClient = useQueryClient();
  const { graphParams } = options;

  // ── Graph query ──────────────────────────────────────────────────────────
  const graphQuery = useQuery({
    queryKey: queryKeys.knowledge.graph(graphParams),
    queryFn: () => fetchGraph(graphParams),
    placeholderData: keepPreviousData,
  });

  // ── Stats query ──────────────────────────────────────────────────────────
  const statsQuery = useQuery({
    queryKey: queryKeys.knowledge.stats(),
    queryFn: fetchStats,
  });

  // ── Hybrid search mutation ────────────────────────────────────────────────
  // Search is request-driven (user-initiated), so useMutation fits better than
  // useQuery; results are imperative and not cacheable across sessions.
  const searchMutation = useMutation({
    mutationFn: ({
      query,
      vectorWeight = 0.5,
      topK = 20,
    }: {
      query: string;
      vectorWeight?: number;
      topK?: number;
    }) => hybridSearch(query, vectorWeight, topK),
  });

  return {
    // graph
    graph: graphQuery.data ?? null,
    isGraphLoading: graphQuery.isLoading,
    graphError: graphQuery.error?.message ?? null,
    refetchGraph: () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.knowledge.graph(graphParams),
      }),

    // stats
    stats: statsQuery.data ?? null,
    isStatsLoading: statsQuery.isLoading,

    // search
    search: searchMutation.mutateAsync,
    searchResults: searchMutation.data ?? [],
    isSearching: searchMutation.isPending,
    searchError: searchMutation.error?.message ?? null,

    // combined loading / error (backward-compat)
    loading: graphQuery.isLoading || searchMutation.isPending,
    error:
      graphQuery.error?.message ?? searchMutation.error?.message ?? null,

    // legacy imperative helpers (kept for backward-compat with pages)
    fetchGraph: (params?: {
      document_id?: string;
      entity_types?: string;
      limit?: number;
    }) =>
      queryClient.fetchQuery({
        queryKey: queryKeys.knowledge.graph(params),
        queryFn: () => fetchGraph(params),
      }),
    fetchStats: () =>
      queryClient.fetchQuery({
        queryKey: queryKeys.knowledge.stats(),
        queryFn: fetchStats,
      }),
  };
}
