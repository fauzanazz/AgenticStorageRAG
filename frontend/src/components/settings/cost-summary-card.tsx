"use client";

import { useState } from "react";
import type { LLMCostSummary } from "@/types/ingestion";
import { DollarSign, ChevronDown, ChevronUp } from "lucide-react";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function CostSummaryCard({ cost }: { cost: LLMCostSummary }) {
  const [expanded, setExpanded] = useState(false);
  const hasModels = Object.keys(cost.by_model).length > 0;

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: "var(--card)", border: "1px solid var(--border)" }}
    >
      <div className="p-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "var(--accent)" }}
          >
            <DollarSign className="size-4" style={{ color: "var(--primary)" }} />
          </div>
          <div>
            <h2 className="text-base font-semibold">LLM API Cost</h2>
            <p className="text-xs mt-0.5" style={{ color: "var(--outline)" }}>
              Total cost:&nbsp;
              <span className="font-semibold">
                {cost.total_cost_usd < 0.0001 && cost.total_cost_usd > 0
                  ? "<$0.0001"
                  : `$${cost.total_cost_usd.toFixed(4)}`}
              </span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="text-right hidden sm:block">
            <p className="text-xs" style={{ color: "var(--outline)" }}>Tokens in</p>
            <p className="text-sm font-semibold">{formatTokens(cost.total_input_tokens)}</p>
          </div>
          <div className="text-right hidden sm:block">
            <p className="text-xs" style={{ color: "var(--outline)" }}>Tokens out</p>
            <p className="text-sm font-semibold">{formatTokens(cost.total_output_tokens)}</p>
          </div>
          <div className="text-right hidden sm:block">
            <p className="text-xs" style={{ color: "var(--outline)" }}>Calls</p>
            <p className="text-sm font-semibold">{cost.total_calls.toLocaleString()}</p>
          </div>

          {hasModels && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="h-8 w-8 rounded-xl flex items-center justify-center transition-all hover:bg-black/5"
              style={{ color: "var(--muted-foreground)" }}
            >
              {expanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
            </button>
          )}
        </div>
      </div>

      {expanded && hasModels && (
        <div
          className="px-4 pb-4 space-y-2"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <p className="pt-3 text-xs font-medium" style={{ color: "var(--muted-foreground)" }}>By model</p>
          {Object.entries(cost.by_model).map(([model, s]) => (
            <div
              key={model}
              className="flex items-center justify-between rounded-xl px-3 py-2 text-xs"
              style={{ background: "var(--card)" }}
            >
              <span className="font-mono truncate max-w-[180px]" style={{ color: "var(--primary)" }}>{model}</span>
              <div className="flex gap-4 shrink-0">
                <span style={{ color: "var(--muted-foreground)" }}>
                  {s.calls} call{s.calls !== 1 ? "s" : ""}
                </span>
                <span style={{ color: "var(--muted-foreground)" }}>
                  {formatTokens(s.input_tokens + s.output_tokens)} tok
                </span>
                <span className="font-semibold">${s.cost_usd.toFixed(4)}</span>
              </div>
            </div>
          ))}
          <p className="text-xs pt-1" style={{ color: "var(--outline-variant)" }}>
            {cost.source === "redis" ? "Aggregated across all workers" : cost.note || ""}
          </p>
        </div>
      )}
    </div>
  );
}
