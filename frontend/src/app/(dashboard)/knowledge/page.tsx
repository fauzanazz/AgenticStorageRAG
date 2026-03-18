"use client";

import { useState } from "react";
import { Search } from "lucide-react";
import { GraphCanvas } from "@/components/knowledge/graph-canvas";
import { StatsCard } from "@/components/knowledge/stats-card";
import { useKnowledge } from "@/hooks/use-knowledge";
import { Skeleton } from "@/components/ui/skeleton";

export default function KnowledgePage() {
  const {
    graph,
    stats,
    searchResults,
    loading,
    error,
    search,
  } = useKnowledge();

  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<"graph" | "search">("graph");

  // No useEffect needed — graph and stats are fetched automatically by
  // the useQuery calls inside useKnowledge on component mount.

  const handleSearch = () => {
    if (searchQuery.trim()) {
      search({ query: searchQuery });
      setActiveTab("search");
    }
  };

  const SOURCE_COLORS: Record<string, { bg: string; color: string }> = {
    vector: { bg: "rgba(59,130,246,0.15)", color: "#60A5FA" },
    graph: { bg: "rgba(34,197,94,0.15)", color: "#4ADE80" },
    hybrid: { bg: "rgba(168,85,247,0.15)", color: "#C084FC" },
  };

  return (
    <div className="flex-1 p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white tracking-tight">Knowledge Graph</h1>
        <p className="mt-1 text-sm" style={{ color: "rgba(255,255,255,0.4)" }}>
          Explore entities, relationships, and search across your knowledge base
        </p>
      </div>

      {/* Stats */}
      <StatsCard stats={stats} />

      {/* Search */}
      <div
        className="flex gap-3 rounded-2xl p-4"
        style={{
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <div className="flex-1 relative">
          <Search
            className="absolute left-4 top-1/2 -translate-y-1/2 size-4"
            style={{ color: "rgba(255,255,255,0.3)" }}
          />
          <input
            placeholder="Search knowledge graph..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            className="w-full h-12 rounded-xl pl-11 pr-4 text-sm text-white placeholder:text-white/30 outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all"
            style={{
              background: "rgba(255,255,255,0.06)",
              border: "1px solid rgba(255,255,255,0.08)",
            }}
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={loading}
          className="h-12 px-6 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50"
          style={{ background: "linear-gradient(135deg, #6366F1, #A855F7)" }}
        >
          {loading ? "Searching..." : "Search"}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-2">
        {(["graph", "search"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className="px-4 py-2 rounded-xl text-sm font-medium transition-all"
            style={{
              background: activeTab === tab ? "rgba(99,102,241,0.12)" : "rgba(255,255,255,0.04)",
              color: activeTab === tab ? "#818CF8" : "rgba(255,255,255,0.5)",
              border: activeTab === tab
                ? "1px solid rgba(99,102,241,0.2)"
                : "1px solid rgba(255,255,255,0.06)",
            }}
          >
            {tab === "graph" ? "Graph View" : `Search Results (${searchResults.length})`}
          </button>
        ))}
      </div>

      {error && (
        <div
          className="rounded-xl px-4 py-3 text-sm"
          style={{
            background: "rgba(239,68,68,0.1)",
            border: "1px solid rgba(239,68,68,0.2)",
            color: "#FCA5A5",
          }}
        >
          {error}
        </div>
      )}

      {/* Content */}
      {activeTab === "graph" && (
        <div
          className="rounded-2xl min-h-[400px] md:min-h-[600px] overflow-hidden"
          style={{
            background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.06)",
          }}
        >
          <div className="h-[400px] md:h-[600px]">
            {graph ? (
              <GraphCanvas data={graph} />
            ) : loading ? (
              <Skeleton className="h-full w-full rounded-none" />
            ) : (
              <div className="flex items-center justify-center h-full">
                <p style={{ color: "rgba(255,255,255,0.4)" }}>No graph data available</p>
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === "search" && (
        <div className="space-y-2">
          {searchResults.length === 0 ? (
            <div
              className="rounded-2xl py-12 text-center"
              style={{
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.06)",
              }}
            >
              <p className="text-sm" style={{ color: "rgba(255,255,255,0.4)" }}>
                {searchQuery
                  ? "No results found. Try a different query."
                  : "Enter a query to search your knowledge base."}
              </p>
            </div>
          ) : (
            searchResults.map((result, index) => (
              <div
                key={index}
                className="rounded-2xl p-4"
                style={{
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid rgba(255,255,255,0.06)",
                }}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-white/80 whitespace-pre-wrap">
                      {result.content}
                    </p>
                    {result.metadata && (
                      <p className="text-xs mt-2" style={{ color: "rgba(255,255,255,0.3)" }}>
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
                    <span className="text-xs" style={{ color: "rgba(255,255,255,0.4)" }}>
                      {(result.score * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
