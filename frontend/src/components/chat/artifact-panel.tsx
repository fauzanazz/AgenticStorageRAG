"use client";

import { Streamdown } from "streamdown";
import { code } from "@streamdown/code";
import { math } from "@streamdown/math";
import "streamdown/styles.css";
import "katex/dist/katex.min.css";
import type { Artifact } from "@/types/chat";

interface ArtifactPanelProps {
  artifact: Artifact | null;
  isStreaming?: boolean;
  onClose: () => void;
}

export function ArtifactPanel({ artifact, isStreaming, onClose }: ArtifactPanelProps) {

  if (!artifact) return null;

  const handleDownload = () => {
    const blob = new Blob([artifact.content], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${artifact.title.replace(/[^a-zA-Z0-9 _-]/g, "_")}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div
      className="flex flex-col h-full"
      style={{
        borderLeft: "1px solid var(--border)",
        background: "var(--card)",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between gap-2 px-4 py-3 shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            style={{ color: "var(--primary)", flexShrink: 0 }}
          >
            <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
          <h3 className="text-sm font-medium truncate">{artifact.title}</h3>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={handleDownload}
            className="rounded-lg p-1.5 transition-colors hover:bg-black/5"
            style={{ color: "var(--muted-foreground)" }}
            title="Download as .md"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" x2="12" y1="15" y2="3" />
            </svg>
          </button>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 transition-colors hover:bg-black/5"
            style={{ color: "var(--muted-foreground)" }}
            title="Close"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" x2="6" y1="6" y2="18" />
              <line x1="6" x2="18" y1="6" y2="18" />
            </svg>
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="prose prose-sm max-w-none dark:prose-invert">
          <Streamdown
            plugins={{ code, math }}
            isAnimating={isStreaming}
          >
            {artifact.content}
          </Streamdown>
        </div>
      </div>
    </div>
  );
}
