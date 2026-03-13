"use client";

import { useEffect, useState } from "react";
import { MobileHeader } from "@/components/layout/mobile-header";
import { GraphCanvas } from "@/components/knowledge/graph-canvas";
import { StatsCard } from "@/components/knowledge/stats-card";
import { useKnowledge } from "@/hooks/use-knowledge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export default function KnowledgePage() {
  const {
    graph,
    stats,
    searchResults,
    loading,
    error,
    fetchGraph,
    fetchStats,
    search,
  } = useKnowledge();

  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<"graph" | "search">("graph");

  useEffect(() => {
    fetchGraph();
    fetchStats();
  }, [fetchGraph, fetchStats]);

  const handleSearch = () => {
    if (searchQuery.trim()) {
      search(searchQuery);
      setActiveTab("search");
    }
  };

  return (
    <>
      <MobileHeader title="Knowledge Graph" />
      <div className="flex flex-col gap-4 p-4 max-w-7xl mx-auto">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold">Knowledge Graph</h1>
          <p className="text-muted-foreground text-sm">
            Explore entities, relationships, and search across your knowledge base
          </p>
        </div>

        {/* Stats */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Statistics</CardTitle>
          </CardHeader>
          <CardContent>
            <StatsCard stats={stats} />
          </CardContent>
        </Card>

        {/* Search */}
        <Card>
          <CardContent className="pt-4">
            <div className="flex gap-2">
              <Input
                placeholder="Search knowledge graph..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                className="flex-1"
              />
              <Button onClick={handleSearch} disabled={loading}>
                {loading ? "Searching..." : "Search"}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Tabs */}
        <div className="flex gap-2">
          <Button
            variant={activeTab === "graph" ? "default" : "outline"}
            size="sm"
            onClick={() => setActiveTab("graph")}
          >
            Graph View
          </Button>
          <Button
            variant={activeTab === "search" ? "default" : "outline"}
            size="sm"
            onClick={() => setActiveTab("search")}
          >
            Search Results ({searchResults.length})
          </Button>
        </div>

        {error && (
          <Card className="border-destructive">
            <CardContent className="pt-4">
              <p className="text-sm text-destructive">{error}</p>
            </CardContent>
          </Card>
        )}

        {/* Content */}
        {activeTab === "graph" && (
          <Card className="min-h-[400px] md:min-h-[600px]">
            <CardContent className="p-0 h-[400px] md:h-[600px]">
              {graph ? (
                <GraphCanvas data={graph} />
              ) : loading ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-muted-foreground">Loading graph...</p>
                </div>
              ) : (
                <div className="flex items-center justify-center h-full">
                  <p className="text-muted-foreground">No graph data available</p>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {activeTab === "search" && (
          <div className="space-y-2">
            {searchResults.length === 0 ? (
              <Card>
                <CardContent className="pt-4">
                  <p className="text-sm text-muted-foreground text-center">
                    {searchQuery
                      ? "No results found. Try a different query."
                      : "Enter a query to search your knowledge base."}
                  </p>
                </CardContent>
              </Card>
            ) : (
              searchResults.map((result, index) => (
                <Card key={index}>
                  <CardContent className="pt-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm whitespace-pre-wrap">
                          {result.content}
                        </p>
                        {result.metadata && (
                          <p className="text-xs text-muted-foreground mt-1">
                            {JSON.stringify(result.metadata)}
                          </p>
                        )}
                      </div>
                      <div className="flex flex-col items-end gap-1 shrink-0">
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                            result.source === "vector"
                              ? "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
                              : result.source === "graph"
                                ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300"
                                : "bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300"
                          }`}
                        >
                          {result.source}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {(result.score * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        )}
      </div>
    </>
  );
}
