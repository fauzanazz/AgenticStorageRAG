"use client";

import type { KnowledgeStats as KnowledgeStatsType } from "@/types/knowledge";

interface StatsCardProps {
  stats: KnowledgeStatsType | null;
}

export function StatsCard({ stats }: StatsCardProps) {
  if (!stats) {
    return (
      <div className="animate-pulse space-y-2">
        <div className="h-4 bg-muted rounded w-1/3" />
        <div className="h-8 bg-muted rounded w-1/2" />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="text-center">
        <p className="text-2xl font-bold">{stats.total_entities}</p>
        <p className="text-xs text-muted-foreground">Entities</p>
      </div>
      <div className="text-center">
        <p className="text-2xl font-bold">{stats.total_relationships}</p>
        <p className="text-xs text-muted-foreground">Relationships</p>
      </div>
      <div className="text-center">
        <p className="text-2xl font-bold">{stats.total_embeddings}</p>
        <p className="text-xs text-muted-foreground">Embeddings</p>
      </div>

      {Object.keys(stats.entity_types).length > 0 && (
        <div className="col-span-3 mt-2">
          <p className="text-xs font-medium text-muted-foreground mb-1">
            Entity Types
          </p>
          <div className="flex flex-wrap gap-1">
            {Object.entries(stats.entity_types).map(([type, count]) => (
              <span
                key={type}
                className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
              >
                {type}: {count}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
