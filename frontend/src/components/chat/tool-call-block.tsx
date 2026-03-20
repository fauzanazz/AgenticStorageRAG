"use client";

import { useState } from "react";
import type { NarrativeStep, ToolResultItem } from "@/types/chat";

interface ToolCallBlockProps {
  step: NarrativeStep;
}

function StatusIcon({ status }: { status: string | undefined }) {
  if (status === "running") {
    return (
      <span className="relative flex h-4 w-4 items-center justify-center">
        <svg
          className="animate-spin"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
        >
          <path d="M21 12a9 9 0 1 1-6.219-8.56" />
        </svg>
      </span>
    );
  }
  if (status === "done") {
    return (
      <span
        className="flex h-4 w-4 items-center justify-center rounded-full"
        style={{ background: "var(--primary)", color: "white" }}
      >
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
          <path d="M20 6 9 17l-5-5" />
        </svg>
      </span>
    );
  }
  if (status === "error") {
    return (
      <span
        className="flex h-4 w-4 items-center justify-center rounded-full"
        style={{ background: "var(--destructive)", color: "white" }}
      >
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
          <path d="M18 6 6 18" />
          <path d="m6 6 12 12" />
        </svg>
      </span>
    );
  }
  return null;
}

function ResultItem({ item }: { item: ToolResultItem }) {
  const isGraph = !!item.entity_name;
  const score = item.similarity ?? item.score ?? item.relevance;

  if (isGraph) {
    return (
      <div
        className="rounded-md border px-2.5 py-2"
        style={{ borderColor: "var(--border)", background: "var(--surface-container-low)" }}
      >
        <div className="flex items-center gap-1.5">
          <span className="font-medium" style={{ color: "var(--foreground)" }}>
            {item.entity_name}
          </span>
          {item.entity_type && (
            <span
              className="rounded px-1 py-0.5 text-[10px]"
              style={{ background: "var(--muted)", color: "var(--muted-foreground)" }}
            >
              {item.entity_type}
            </span>
          )}
          {score != null && (
            <span className="ml-auto text-[10px] tabular-nums" style={{ color: "var(--muted-foreground)" }}>
              {score.toFixed(2)}
            </span>
          )}
        </div>
        {item.description && (
          <p className="mt-1 leading-snug" style={{ color: "var(--muted-foreground)" }}>
            {item.description}
          </p>
        )}
        {item.relationships && item.relationships.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {item.relationships.map((rel, i) => (
              <span
                key={i}
                className="rounded px-1 py-0.5 text-[10px]"
                style={{ background: "var(--muted)", color: "var(--muted-foreground)" }}
              >
                {rel.type} → {rel.target}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }

  // Vector / hybrid search result
  return (
    <div
      className="rounded-md border px-2.5 py-2"
      style={{ borderColor: "var(--border)", background: "var(--surface-container-low)" }}
    >
      <div className="flex items-center gap-1.5 mb-1">
        {item.source && (
          <span
            className="rounded px-1 py-0.5 text-[10px]"
            style={{ background: "var(--muted)", color: "var(--muted-foreground)" }}
          >
            {item.source}
          </span>
        )}
        {score != null && (
          <span className="ml-auto text-[10px] tabular-nums" style={{ color: "var(--muted-foreground)" }}>
            {score.toFixed(2)}
          </span>
        )}
      </div>
      {item.content && (
        <p className="leading-snug" style={{ color: "var(--muted-foreground)" }}>
          {item.content}
        </p>
      )}
    </div>
  );
}

export function ToolCallBlock({ step }: ToolCallBlockProps) {
  const [expanded, setExpanded] = useState(false);

  const label = step.tool_label || step.tool_name || "Tool call";
  const isRunning = step.tool_status === "running";
  const isDone = step.tool_status === "done";
  const hasResults = step.tool_results && step.tool_results.length > 0;

  return (
    <div
      className="mb-2 animate-in fade-in slide-in-from-bottom-1 duration-300 rounded-lg border"
      style={{
        borderColor: "var(--border)",
        background: "var(--card)",
        animationFillMode: "both",
      }}
    >
      {/* Header — always visible */}
      <button
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm transition-colors hover:bg-black/[0.02]"
      >
        <StatusIcon status={step.tool_status} />

        <span className="flex-1 font-medium" style={{ color: "var(--foreground)" }}>
          {label}
          {isRunning && (
            <span className="ml-1" style={{ color: "var(--muted-foreground)" }}>...</span>
          )}
        </span>

        {isDone && step.tool_summary && (
          <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>
            {step.tool_summary}
          </span>
        )}

        {step.tool_duration_ms != null && step.tool_duration_ms > 0 && (
          <span className="text-[10px] tabular-nums" style={{ color: "var(--muted-foreground)" }}>
            {step.tool_duration_ms < 1000
              ? `${step.tool_duration_ms}ms`
              : `${(step.tool_duration_ms / 1000).toFixed(1)}s`}
          </span>
        )}

        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className={`shrink-0 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
          style={{ color: "var(--muted-foreground)" }}
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {/* Expanded details */}
      <div
        className="overflow-hidden transition-all duration-200 ease-out"
        style={{
          maxHeight: expanded ? "500px" : "0",
          opacity: expanded ? 1 : 0,
        }}
      >
        <div
          className="border-t px-3 py-2 text-xs overflow-y-auto"
          style={{ borderColor: "var(--border)", color: "var(--muted-foreground)", maxHeight: "480px" }}
        >
          {step.tool_args && Object.keys(step.tool_args).length > 0 && (
            <div className="mb-1.5">
              <span className="font-medium">Query: </span>
              {String(step.tool_args.query || step.tool_args.search_query || JSON.stringify(step.tool_args))}
            </div>
          )}
          {hasResults ? (
            <div className="mt-2 space-y-2">
              {step.tool_results!.map((item, idx) => (
                <ResultItem key={idx} item={item} />
              ))}
            </div>
          ) : step.tool_count != null ? (
            <div>
              <span className="font-medium">Results: </span>
              {step.tool_count} items found
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
