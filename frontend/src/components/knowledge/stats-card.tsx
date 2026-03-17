"use client";

import type { KnowledgeStats as KnowledgeStatsType } from "@/types/knowledge";
import { Skeleton } from "@/components/ui/skeleton";

const ENTITY_TYPE_COLORS: Record<string, string> = {
  Person: "#60A5FA",
  Organization: "#4ADE80",
  Concept: "#C084FC",
  Technology: "#FBBF24",
  Event: "#FCA5A5",
  Location: "#22D3EE",
};

interface StatsCardProps {
  stats: KnowledgeStatsType | null;
}

export function StatsCard({ stats }: StatsCardProps) {
  if (!stats) {
    return (
      <div className="grid grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-24 rounded-2xl" />
        ))}
      </div>
    );
  }

  const statItems = [
    { label: "Entities", value: stats.total_entities, color: "#6366F1" },
    { label: "Relationships", value: stats.total_relationships, color: "#A855F7" },
    { label: "Embeddings", value: stats.total_embeddings, color: "#22D3EE" },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        {statItems.map((item) => (
          <div
            key={item.label}
            className="rounded-2xl p-5 text-center"
            style={{
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.06)",
            }}
          >
            <p className="text-3xl font-bold text-white">{item.value}</p>
            <p className="text-xs mt-1" style={{ color: "rgba(255,255,255,0.4)" }}>
              {item.label}
            </p>
          </div>
        ))}
      </div>

      {Object.keys(stats.entity_types).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(stats.entity_types).map(([type, count]) => {
            const color = ENTITY_TYPE_COLORS[type] || "#818CF8";
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
