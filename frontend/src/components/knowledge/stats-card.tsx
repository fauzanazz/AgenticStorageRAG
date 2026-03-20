"use client";

import type { KnowledgeStats as KnowledgeStatsType } from "@/types/knowledge";
import { Skeleton } from "@/components/ui/skeleton";

const ENTITY_TYPE_COLORS: Record<string, string> = {
  Person: "#1565c0",
  Organization: "#2e7d32",
  Concept: "#625b77",
  Technology: "#e65100",
  Event: "#9e3f4e",
  Location: "#0277bd",
};

interface StatsCardProps {
  stats: KnowledgeStatsType | null;
}

export function StatsCard({ stats }: StatsCardProps) {
  if (!stats) {
    return (
      <div className="grid grid-cols-3 lg:grid-cols-1 gap-4">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-24 rounded-2xl" />
        ))}
      </div>
    );
  }

  const statItems = [
    { label: "Entities", value: stats.total_entities, color: "var(--primary)" },
    { label: "Relationships", value: stats.total_relationships, color: "var(--tertiary)" },
    { label: "Embeddings", value: stats.total_embeddings, color: "var(--chart-3)" },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 lg:grid-cols-1 gap-4">
        {statItems.map((item) => (
          <div
            key={item.label}
            className="rounded-2xl p-5 text-center"
            style={{
              background: "var(--card)",
              border: "1px solid var(--border)",
            }}
          >
            <p className="text-3xl font-bold">{item.value}</p>
            <p className="text-xs mt-1" style={{ color: "var(--muted-foreground)" }}>
              {item.label}
            </p>
          </div>
        ))}
      </div>

      {Object.keys(stats.entity_types).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(stats.entity_types).map(([type, count]) => {
            const color = ENTITY_TYPE_COLORS[type] || "var(--primary)";
            return (
              <span
                key={type}
                className="inline-flex items-center rounded-full px-3 py-1 text-xs font-medium"
                style={{
                  background: `${color}20`,
                  color: color,
                }}
              >
                {type}: {count}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
