"use client";

import { useCallback, useState } from "react";
import { Search } from "lucide-react";
import { GraphCanvas } from "@/components/knowledge/graph-canvas";
import { StatsCard } from "@/components/knowledge/stats-card";
import { useKnowledge } from "@/hooks/use-knowledge";
import { Skeleton } from "@/components/ui/skeleton";
import type { GraphVisualization } from "@/types/knowledge";

type SourceTab = "all" | "upload" | "google_drive";

export default function KnowledgePage() {
  const [sourceTab, setSourceTab] = useState<SourceTab>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedGraph, setExpandedGraph] = useState<GraphVisualization | null>(null);
  const [nodeLimit, setNodeLimit] = useState(500);

  const graphSource = sourceTab === "all" ? undefined : sourceTab;

  const {
    graph,
    stats,
    searchResults,
    loading,
    error,
    search,
    fetchNeighbors,
  } = useKnowledge({
    graphParams: {
      ...(graphSource ? { source: graphSource } : {}),
      limit: nodeLimit,
    },
  });

  // Merge base graph with any expanded neighbor data
  const displayGraph = expandedGraph
    ? mergeGraphs(graph, expandedGraph)
    : graph;

  const handleSearch = () => {
    if (searchQuery.trim()) {
      search({ query: searchQuery });
    }
  };

  const handleExpandNode = useCallback(
    async (nodeId: string): Promise<GraphVisualization | null> => {
      try {
        const neighbors = await fetchNeighbors(nodeId, 1, 50);
        if (neighbors && neighbors.nodes.length > 0) {
          setExpandedGraph((prev) =>
            prev ? mergeGraphs(prev, neighbors) : neighbors
          );
        }
        return neighbors;
      } catch {
        return null;
      }
    },
    [fetchNeighbors]
  );

  // Reset expanded graph when source tab changes
  const handleSourceChange = (tab: SourceTab) => {
    setSourceTab(tab);
    setExpandedGraph(null);
  };

  const SOURCE_COLORS: Record<string, { bg: string; color: string }> = {
    vector: { bg: "#e3f2fd", color: "#1565c0" },
    graph: { bg: "#e8f5e9", color: "#2e7d32" },
    hybrid: { bg: "#f3e5f5", color: "#625b77" },
  };

  const sourceTabs: { key: SourceTab; label: string }[] = [
    { key: "all", label: "All Sources" },
    { key: "upload", label: "Uploads KG" },
    { key: "google_drive", label: "Drive KG" },
  ];

  return (
    <div className="flex-1 p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Knowledge Graph</h1>
        <p className="mt-1 text-sm" style={{ color: "var(--muted-foreground)" }}>
          Explore entities, relationships, and search across your knowledge base
        </p>
      </div>

      {error && (
        <div
          className="rounded-xl px-4 py-3 text-sm"
          style={{
            background: "var(--error-container)",
            border: "1px solid color-mix(in srgb, var(--destructive) 20%, transparent)",
            color: "var(--destructive)",
          }}
        >
          {error}
        </div>
      )}

      {/* Split layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left sidebar */}
        <div className="lg:col-span-1 space-y-6">
          {/* Stats */}
          <StatsCard stats={stats} />

          {/* Source filter */}
          <div className="flex flex-wrap gap-2">
            {sourceTabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => handleSourceChange(tab.key)}
                className="px-4 py-2 rounded-xl text-sm font-medium transition-all"
                style={{
                  background: sourceTab === tab.key ? "var(--accent)" : "var(--muted)",
                  color: sourceTab === tab.key ? "var(--primary)" : "var(--muted-foreground)",
                  border: sourceTab === tab.key
                    ? "1px solid color-mix(in srgb, var(--primary) 20%, transparent)"
                    : "1px solid var(--border)",
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Node limit slider */}
          <div
            className="rounded-2xl px-4 py-3 space-y-2"
            style={{
              background: "var(--card)",
              border: "1px solid var(--border)",
            }}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium" style={{ color: "var(--muted-foreground)" }}>
                Nodes to load
              </span>
              <span className="text-xs tabular-nums" style={{ color: "var(--on-surface-variant)" }}>
                {nodeLimit}
              </span>
            </div>
            <input
              type="range"
              min={100}
              max={5000}
              step={100}
              value={nodeLimit}
              onChange={(e) => setNodeLimit(Number(e.target.value))}
              className="w-full accent-primary"
            />
          </div>

          {/* Search */}
          <div
            className="rounded-2xl p-4 space-y-3"
            style={{
              background: "var(--card)",
              border: "1px solid var(--border)",
            }}
          >
            <div className="relative">
              <Search
                className="absolute left-4 top-1/2 -translate-y-1/2 size-4"
                style={{ color: "var(--outline)" }}
              />
              <input
                placeholder="Search knowledge graph..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                className="w-full h-12 rounded-xl pl-11 pr-4 text-sm placeholder:text-outline-variant outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                style={{
                  background: "var(--surface-container-high)",
                  border: "1px solid var(--outline-variant)",
                }}
              />
            </div>
            <button
              onClick={handleSearch}
              disabled={loading}
              className="w-full h-12 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50"
              style={{ background: "var(--primary)" }}
            >
              {loading ? "Searching..." : "Search"}
            </button>
          </div>
        </div>

        {/* Right column — graph + search results */}
        <div className="lg:col-span-2 space-y-6">
          {/* Graph canvas */}
          <div
            className="rounded-2xl overflow-hidden"
            style={{
              background: "var(--card)",
              border: "1px solid var(--border)",
            }}
          >
            <div className="h-[400px] lg:h-[calc(100dvh-14rem)]">
              {displayGraph ? (
                <GraphCanvas data={displayGraph} onExpandNode={handleExpandNode} />
              ) : loading ? (
                <Skeleton className="h-full w-full rounded-none" />
              ) : (
                <div className="flex items-center justify-center h-full">
                  <p style={{ color: "var(--muted-foreground)" }}>No graph data available</p>
                </div>
              )}
            </div>
          </div>

          {/* Search results — shown below graph when present */}
          {searchResults.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-sm font-semibold" style={{ color: "var(--muted-foreground)" }}>
                Search Results ({searchResults.length})
              </h3>
              {searchResults.map((result, index) => (
                <div
                  key={result.chunk_id ?? result.entity_id ?? `${result.source}-${index}`}
                  className="rounded-2xl p-4"
                  style={{
                    background: "var(--card)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-[#323235cc] whitespace-pre-wrap">
                        {result.content}
                      </p>
                      {result.metadata && (
                        <p className="text-xs mt-2" style={{ color: "var(--outline)" }}>
                          {JSON.stringify(result.metadata)}
                        </p>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-1.5 shrink-0">
                      <span
                        className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium"
                        style={SOURCE_COLORS[result.source] || SOURCE_COLORS.hybrid}
                      >
                        {result.source}
                      </span>
                      <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                        {(result.score * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Merge two graph visualizations, deduplicating nodes and edges.
 */
function mergeGraphs(
  base: GraphVisualization | null,
  overlay: GraphVisualization
): GraphVisualization {
  if (!base) return overlay;

  const nodeMap = new Map(base.nodes.map((n) => [n.id, n]));
  for (const n of overlay.nodes) {
    if (!nodeMap.has(n.id)) nodeMap.set(n.id, n);
  }

  const edgeSet = new Set(
    base.edges.map((e) => `${e.source}:${e.target}:${e.label}`)
  );
  const mergedEdges = [...base.edges];
  for (const e of overlay.edges) {
    const key = `${e.source}:${e.target}:${e.label}`;
    if (!edgeSet.has(key)) {
      edgeSet.add(key);
      mergedEdges.push(e);
    }
  }

  return {
    nodes: Array.from(nodeMap.values()),
    edges: mergedEdges,
    total_nodes: Math.max(base.total_nodes, overlay.total_nodes),
    total_edges: Math.max(base.total_edges, overlay.total_edges),
  };
}
