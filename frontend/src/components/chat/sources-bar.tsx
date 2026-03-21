"use client";

import { useState } from "react";
import type { Citation } from "@/types/chat";

interface SourcesBarProps {
  citations: Citation[];
}

function SourceCard({
  citation,
  index,
}: {
  citation: Citation;
  index: number;
}) {
  const [showSnippet, setShowSnippet] = useState(false);
  const isDrive = citation.source_url?.includes("drive.google.com");
  const hasUrl = !!citation.source_url;

  if (hasUrl) {
    return (
      <a
        href={citation.source_url!}
        target="_blank"
        rel="noopener noreferrer"
        className="flex shrink-0 items-center gap-2 rounded-lg border px-3 py-2 text-xs transition-colors hover:bg-black/[0.04]"
        style={{
          borderColor: "var(--border)",
          color: "var(--foreground)",
          cursor: "pointer",
        }}
      >
        <span
          className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-[10px] font-bold text-white"
          style={{
            background: isDrive ? "#4285F4" : "var(--primary)",
          }}
        >
          {isDrive ? "G" : index + 1}
        </span>
        <div className="min-w-0">
          <p className="truncate font-medium" style={{ maxWidth: "140px" }}>
            {citation.document_name || `Source ${index + 1}`}
          </p>
          {citation.page_number && (
            <p style={{ color: "var(--muted-foreground)" }}>
              p.{citation.page_number}
            </p>
          )}
        </div>
      </a>
    );
  }

  // Graph-only citation: show snippet on click
  return (
    <div className="relative shrink-0">
      <button
        type="button"
        onClick={() => setShowSnippet((v) => !v)}
        className="flex items-center gap-2 rounded-lg border px-3 py-2 text-xs transition-colors hover:bg-black/[0.04]"
        style={{
          borderColor: "var(--border)",
          color: "var(--foreground)",
          cursor: "pointer",
        }}
      >
        <span
          className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-[10px] font-bold text-white"
          style={{ background: "#6B7280" }}
        >
          K
        </span>
        <div className="min-w-0 text-left">
          <p className="truncate font-medium" style={{ maxWidth: "140px" }}>
            {citation.document_name || `Source ${index + 1}`}
          </p>
          <p style={{ color: "var(--muted-foreground)" }}>Knowledge Graph</p>
        </div>
      </button>
      {showSnippet && citation.chunk_text && (
        <div
          className="absolute bottom-full left-0 z-10 mb-1 w-72 rounded-lg border p-3 text-xs shadow-lg"
          style={{
            background: "var(--popover)",
            borderColor: "var(--border)",
            color: "var(--foreground)",
          }}
        >
          <p className="whitespace-pre-wrap">{citation.chunk_text}</p>
        </div>
      )}
    </div>
  );
}

export function SourcesBar({ citations }: SourcesBarProps) {
  if (citations.length === 0) return null;

  // Deduplicate by document_id, entity_id, or document_name
  const seen = new Set<string>();
  const unique = citations.filter((c) => {
    const key = c.document_id || c.entity_id || c.document_name;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  return (
    <div className="mb-2">
      <p
        className="mb-1.5 text-[11px] font-medium uppercase tracking-wider"
        style={{ color: "var(--muted-foreground)" }}
      >
        Sources
      </p>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {unique.map((citation, i) => (
          <SourceCard
            key={citation.document_id || citation.entity_id || i}
            citation={citation}
            index={i}
          />
        ))}
      </div>
    </div>
  );
}
