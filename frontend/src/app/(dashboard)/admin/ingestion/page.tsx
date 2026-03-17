"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw, ChevronDown, ChevronUp, DollarSign, FileText, CheckCircle2, Clock, XCircle, SkipForward } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { useIngestion } from "@/hooks/use-ingestion";
import type { FileEvent, FileEvents, IngestionJob, IngestionStatus, LLMCostSummary } from "@/types/ingestion";
import { Skeleton } from "@/components/ui/skeleton";

// ── Status config ────────────────────────────────────────────────────────────

const STATUS_STYLES: Record<IngestionStatus, { bg: string; color: string; label: string }> = {
  pending:    { bg: "rgba(245,158,11,0.15)", color: "#FBBF24", label: "Queued" },
  scanning:   { bg: "rgba(59,130,246,0.15)", color: "#60A5FA", label: "Scanning" },
  processing: { bg: "rgba(99,102,241,0.15)", color: "#818CF8", label: "Processing" },
  completed:  { bg: "rgba(34,197,94,0.15)",  color: "#4ADE80", label: "Completed" },
  failed:     { bg: "rgba(239,68,68,0.15)",  color: "#FCA5A5", label: "Failed" },
  cancelled:  { bg: "rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.4)", label: "Cancelled" },
};

function StatusBadge({ status }: { status: IngestionStatus }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.pending;
  const isActive = status === "scanning" || status === "processing";
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium"
      style={{ background: s.bg, color: s.color }}
    >
      {isActive && (
        <span
          className="inline-block h-1.5 w-1.5 animate-pulse rounded-full"
          style={{ background: "currentColor" }}
        />
      )}
      {s.label}
    </span>
  );
}

// ── Progress bar ─────────────────────────────────────────────────────────────

function ProgressBar({ job }: { job: IngestionJob }) {
  if (job.total_files === 0) return null;
  const done = job.processed_files + job.failed_files + job.skipped_files;
  const pct = Math.min((done / job.total_files) * 100, 100);

  return (
    <div className="mt-3 space-y-1">
      <div className="flex justify-between text-xs" style={{ color: "rgba(255,255,255,0.4)" }}>
        <span>
          <span style={{ color: "#4ADE80" }}>{job.processed_files}</span> processed
          {job.failed_files > 0 && (
            <> · <span style={{ color: "#FCA5A5" }}>{job.failed_files}</span> failed</>
          )}
          {job.skipped_files > 0 && (
            <> · <span style={{ color: "#FBBF24" }}>{job.skipped_files}</span> skipped</>
          )}
        </span>
        <span>{job.total_files} total</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: "linear-gradient(90deg, #6366F1, #A855F7)" }}
        />
      </div>
    </div>
  );
}

// ── File list ─────────────────────────────────────────────────────────────────

const FILE_STATE_STYLES: Record<FileEvent["state"], { icon: React.JSX.Element; color: string; label: string }> = {
  started:   { icon: <Clock className="size-3" />,         color: "#818CF8", label: "Ingesting" },
  completed: { icon: <CheckCircle2 className="size-3" />,  color: "#4ADE80", label: "Done" },
  skipped:   { icon: <SkipForward className="size-3" />,   color: "#FBBF24", label: "Skipped" },
  failed:    { icon: <XCircle className="size-3" />,       color: "#FCA5A5", label: "Failed" },
};

function FileList({ fileEvents }: { fileEvents: FileEvents }) {
  const entries = Object.entries(fileEvents);
  if (entries.length === 0) return null;

  // Sort: started first (active), then by timestamp desc
  const sorted = entries.sort(([, a], [, b]) => {
    if (a.state === "started" && b.state !== "started") return -1;
    if (b.state === "started" && a.state !== "started") return 1;
    return new Date(b.ts).getTime() - new Date(a.ts).getTime();
  });

  return (
    <div
      className="mt-3 rounded-xl overflow-hidden"
      style={{ background: "rgba(0,0,0,0.3)", border: "1px solid rgba(255,255,255,0.05)" }}
    >
      <div
        className="px-3 py-2 text-xs font-medium flex items-center gap-1.5"
        style={{ color: "rgba(255,255,255,0.5)", borderBottom: "1px solid rgba(255,255,255,0.05)" }}
      >
        <FileText className="size-3" />
        Files
        <span className="ml-auto" style={{ color: "rgba(255,255,255,0.3)" }}>
          {entries.filter(([, e]) => e.state === "completed").length}/{entries.length}
        </span>
      </div>
      <div className="max-h-52 overflow-y-auto divide-y" style={{ borderColor: "rgba(255,255,255,0.04)" }}>
        {sorted.map(([fileId, ev]) => {
          const style = FILE_STATE_STYLES[ev.state];
          const shortFolder = ev.folder?.split("/").slice(-2).join(" › ") ?? "";
          return (
            <div key={fileId} className="flex items-center gap-2 px-3 py-2">
              <span style={{ color: style.color }} className="shrink-0">{style.icon}</span>
              <div className="flex-1 min-w-0">
                <p
                  className="text-xs font-medium truncate"
                  style={{ color: ev.state === "started" ? "white" : "rgba(255,255,255,0.6)" }}
                >
                  {ev.name}
                </p>
                {shortFolder && (
                  <p className="text-[10px] truncate" style={{ color: "rgba(255,255,255,0.25)" }}>
                    {shortFolder}
                  </p>
                )}
              </div>
              <div className="shrink-0 text-right">
                <span className="text-[10px] font-medium" style={{ color: style.color }}>{style.label}</span>
                {ev.state === "completed" && ev.chunks != null && (
                  <p className="text-[10px]" style={{ color: "rgba(255,255,255,0.25)" }}>
                    {ev.chunks} chunks
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Job card ─────────────────────────────────────────────────────────────────

function JobCard({ job, onCancel }: { job: IngestionJob; onCancel: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const isActive = ["pending", "scanning", "processing"].includes(job.status);
  const meta = job.metadata;
  const fileEvents = meta.file_events ?? {};
  const fileCount = Object.keys(fileEvents).length;
  const hasSummary = !!meta.orchestrator_summary;
  const hasExpandable = fileCount > 0 || hasSummary;

  // Auto-expand for active jobs with file events
  const activeFile = Object.values(fileEvents).find((e) => e.state === "started");

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
    >
      {/* Header row */}
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex items-center gap-2 flex-wrap">
              <StatusBadge status={job.status} />
              <span className="text-xs" style={{ color: "rgba(255,255,255,0.3)" }}>
                {new Date(job.started_at).toLocaleString()}
              </span>
              {job.completed_at && (
                <span className="text-xs" style={{ color: "rgba(255,255,255,0.3)" }}>
                  · {Math.round((new Date(job.completed_at).getTime() - new Date(job.started_at).getTime()) / 1000)}s
                </span>
              )}
            </div>

            <p className="text-sm font-medium text-white">
              {job.source === "google_drive" ? "Google Drive" : job.source}
              {job.folder_id && (
                <span className="ml-1 font-mono text-xs" style={{ color: "rgba(255,255,255,0.3)" }}>
                  ({job.folder_id.slice(0, 16)}…)
                </span>
              )}
            </p>

            {/* Currently ingesting file */}
            {isActive && activeFile && (
              <p className="text-xs flex items-center gap-1.5" style={{ color: "#818CF8" }}>
                <Clock className="size-3 shrink-0" />
                <span className="truncate">{activeFile.name}</span>
              </p>
            )}
            {/* Pending: waiting for worker */}
            {job.status === "pending" && (
              <p className="text-xs flex items-center gap-1.5" style={{ color: "#FBBF24" }}>
                <Clock className="size-3 shrink-0" />
                Waiting for worker to become available…
              </p>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {isActive && (
              <button
                onClick={() => onCancel(job.id)}
                className="h-8 px-3 rounded-xl text-xs font-medium transition-all hover:opacity-80"
                style={{ border: "1px solid rgba(255,255,255,0.1)", color: "rgba(255,255,255,0.5)" }}
              >
                Cancel
              </button>
            )}
            {hasExpandable && (
              <button
                onClick={() => setExpanded((v) => !v)}
                className="h-8 w-8 rounded-xl flex items-center justify-center transition-all hover:bg-white/5"
                style={{ color: "rgba(255,255,255,0.4)" }}
              >
                {expanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
              </button>
            )}
          </div>
        </div>

        <ProgressBar job={job} />

        {job.error_message && (
          <p className="mt-2 text-xs" style={{ color: "#FCA5A5" }}>
            {job.error_message}
          </p>
        )}
      </div>

      {/* Expanded: file list + summary */}
      {expanded && (
        <div
          className="px-5 pb-5 space-y-3"
          style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}
        >
          {fileCount > 0 && <FileList fileEvents={fileEvents} />}

          {hasSummary && (
            <div
              className="rounded-xl p-3 text-xs"
              style={{ background: "rgba(99,102,241,0.08)", color: "rgba(255,255,255,0.65)" }}
            >
              <p className="font-medium mb-1" style={{ color: "#818CF8" }}>Orchestrator Summary</p>
              <p className="whitespace-pre-wrap">{meta.orchestrator_summary}</p>
            </div>
          )}

          {meta.orchestrator_warning && (
            <div
              className="rounded-xl p-3 text-xs"
              style={{ background: "rgba(245,158,11,0.08)", color: "#FBBF24" }}
            >
              <p className="font-medium">Warning</p>
              <p>{meta.orchestrator_warning}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Cost summary card ─────────────────────────────────────────────────────────

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function CostSummaryCard({ cost }: { cost: LLMCostSummary }) {
  const [expanded, setExpanded] = useState(false);
  const hasModels = Object.keys(cost.by_model).length > 0;

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
    >
      <div className="p-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: "rgba(99,102,241,0.15)" }}
          >
            <DollarSign className="size-4" style={{ color: "#818CF8" }} />
          </div>
          <div>
            <p className="text-xs font-medium" style={{ color: "rgba(255,255,255,0.5)" }}>
              LLM Cost (session)
            </p>
            <p className="text-xl font-bold text-white">
              ${cost.total_cost_usd < 0.0001 && cost.total_cost_usd > 0
                ? "<$0.0001"
                : `$${cost.total_cost_usd.toFixed(4)}`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="text-right hidden sm:block">
            <p className="text-xs" style={{ color: "rgba(255,255,255,0.35)" }}>Tokens in</p>
            <p className="text-sm font-semibold text-white">{formatTokens(cost.total_input_tokens)}</p>
          </div>
          <div className="text-right hidden sm:block">
            <p className="text-xs" style={{ color: "rgba(255,255,255,0.35)" }}>Tokens out</p>
            <p className="text-sm font-semibold text-white">{formatTokens(cost.total_output_tokens)}</p>
          </div>
          <div className="text-right hidden sm:block">
            <p className="text-xs" style={{ color: "rgba(255,255,255,0.35)" }}>Calls</p>
            <p className="text-sm font-semibold text-white">{cost.total_calls.toLocaleString()}</p>
          </div>

          {hasModels && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="h-8 w-8 rounded-xl flex items-center justify-center transition-all hover:bg-white/5"
              style={{ color: "rgba(255,255,255,0.4)" }}
            >
              {expanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
            </button>
          )}
        </div>
      </div>

      {expanded && hasModels && (
        <div
          className="px-4 pb-4 space-y-2"
          style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}
        >
          <p className="pt-3 text-xs font-medium" style={{ color: "rgba(255,255,255,0.4)" }}>By model</p>
          {Object.entries(cost.by_model).map(([model, s]) => (
            <div
              key={model}
              className="flex items-center justify-between rounded-xl px-3 py-2 text-xs"
              style={{ background: "rgba(255,255,255,0.03)" }}
            >
              <span className="font-mono truncate max-w-[180px]" style={{ color: "#818CF8" }}>{model}</span>
              <div className="flex gap-4 shrink-0">
                <span style={{ color: "rgba(255,255,255,0.5)" }}>
                  {s.calls} call{s.calls !== 1 ? "s" : ""}
                </span>
                <span style={{ color: "rgba(255,255,255,0.5)" }}>
                  {formatTokens(s.input_tokens + s.output_tokens)} tok
                </span>
                <span className="font-semibold text-white">${s.cost_usd.toFixed(4)}</span>
              </div>
            </div>
          ))}
          <p className="text-xs pt-1" style={{ color: "rgba(255,255,255,0.2)" }}>
            {cost.source === "redis" ? "Aggregated across all workers" : cost.note || ""}
          </p>
        </div>
      )}
    </div>
  );
}

// ── Stats bar ─────────────────────────────────────────────────────────────────

function StatsBar({ stats }: { stats: NonNullable<ReturnType<typeof useIngestion>["stats"]> }) {
  const items = [
    { label: "Total Jobs",     value: stats.total_jobs },
    { label: "Files Processed", value: stats.total_files_processed, color: "#4ADE80" },
    { label: "Files Failed",   value: stats.total_files_failed, color: stats.total_files_failed > 0 ? "#FCA5A5" : undefined },
    { label: "Files Skipped",  value: stats.total_files_skipped, color: stats.total_files_skipped > 0 ? "#FBBF24" : undefined },
  ];

  return (
    <div
      className="grid grid-cols-2 sm:grid-cols-4 gap-3"
    >
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-2xl p-4"
          style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
        >
          <p className="text-2xl font-bold" style={{ color: item.color ?? "white" }}>
            {item.value.toLocaleString()}
          </p>
          <p className="text-xs mt-0.5" style={{ color: "rgba(255,255,255,0.4)" }}>{item.label}</p>
        </div>
      ))}
    </div>
  );
}

// ── Worker state ──────────────────────────────────────────────────────────────

function WorkerState({ stats }: { stats: NonNullable<ReturnType<typeof useIngestion>["stats"]> }) {
  const statusOrder: IngestionStatus[] = ["processing", "scanning", "pending", "completed", "failed", "cancelled"];

  return (
    <div
      className="rounded-2xl p-5"
      style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
    >
      <p className="text-sm font-semibold text-white mb-3">Job Distribution</p>
      <div className="flex flex-wrap gap-2">
        {statusOrder.map((s) => {
          const count = stats.jobs_by_status[s] ?? 0;
          if (count === 0) return null;
          const style = STATUS_STYLES[s];
          return (
            <span
              key={s}
              className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium"
              style={{ background: style.bg, color: style.color }}
            >
              {style.label}
              <span
                className="rounded-full px-1.5 py-px text-[10px] font-bold"
                style={{ background: "rgba(0,0,0,0.3)" }}
              >
                {count}
              </span>
            </span>
          );
        })}
      </div>

      {/* Active job mini-view */}
      {stats.active_job && (
        <div className="mt-4 pt-4" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
          <p className="text-xs font-medium mb-2" style={{ color: "rgba(255,255,255,0.5)" }}>Active Job</p>
          <div className="flex items-center justify-between gap-2">
            <StatusBadge status={stats.active_job.status} />
            <span className="text-xs text-white truncate flex-1 text-right">
              {stats.active_job.processed_files}/{stats.active_job.total_files} files
            </span>
          </div>
          {stats.active_job.metadata?.current_action && (
            <p className="mt-1.5 text-xs" style={{ color: "#818CF8" }}>
              {stats.active_job.metadata.current_action}
            </p>
          )}
          {stats.active_job.total_files > 0 && <ProgressBar job={stats.active_job} />}
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function IngestionPage() {
  const { user } = useAuth();
  const router = useRouter();
  const {
    jobs,
    stats,
    costSummary,
    isLoading,
    isTriggering,
    error,
    refresh,
    triggerIngestion,
    cancelJob,
    setError,
  } = useIngestion();

  // Admin guard
  useEffect(() => {
    if (user && !user.is_admin) {
      router.replace("/");
    }
  }, [user, router]);

  // Initial load
  useEffect(() => {
    if (user?.is_admin) {
      refresh();
    }
  }, [refresh, user]);

  // Poll every 4s when there are active jobs
  useEffect(() => {
    const hasActive = jobs.some((j) =>
      ["pending", "scanning", "processing"].includes(j.status)
    );
    if (!hasActive) return;

    const id = setInterval(() => refresh(), 4000);
    return () => clearInterval(id);
  }, [jobs, refresh]);

  return (
    <div className="flex-1 p-6 lg:p-8 space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white tracking-tight">Base Knowledge Ingestion</h1>
        <p className="mt-1 text-sm" style={{ color: "rgba(255,255,255,0.4)" }}>
          Agent orchestrator that recursively explores Google Drive, classifies documents, and builds the Knowledge Graph.
        </p>
      </div>

      {/* Actions */}
      <div className="flex gap-3 flex-wrap">
        <button
          onClick={() => triggerIngestion()}
          disabled={isTriggering}
          className="h-10 px-5 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50"
          style={{ background: "linear-gradient(135deg, #6366F1, #A855F7)" }}
        >
          {isTriggering ? "Starting..." : "Ingest from Drive"}
        </button>
        <button
          onClick={() => triggerIngestion({ force: true })}
          disabled={isTriggering}
          className="h-10 px-5 rounded-xl text-sm font-medium transition-all hover:opacity-80"
          style={{ border: "1px solid rgba(255,255,255,0.1)", color: "rgba(255,255,255,0.6)" }}
        >
          Force Re-ingest All
        </button>
        <button
          onClick={() => refresh()}
          className="h-10 px-4 rounded-xl flex items-center gap-2 text-sm font-medium transition-all hover:bg-white/5"
          style={{ color: "rgba(255,255,255,0.5)" }}
        >
          <RefreshCw className="size-4" />
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div
          className="flex items-center justify-between rounded-xl px-4 py-3 text-sm"
          style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)", color: "#FCA5A5" }}
        >
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-2 hover:opacity-70">Dismiss</button>
        </div>
      )}

      {/* Stats bar */}
      {stats && <StatsBar stats={stats} />}

      {/* Cost summary */}
      {costSummary && <CostSummaryCard cost={costSummary} />}

      {/* Two-column: job list + worker state */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Job list (2/3) */}
        <div className="lg:col-span-2 space-y-3">
          <h2 className="text-sm font-medium text-white">
            Ingestion Jobs
            <span className="ml-2 text-xs" style={{ color: "rgba(255,255,255,0.3)" }}>({jobs.length})</span>
          </h2>

          {isLoading && jobs.length === 0 ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-24 rounded-2xl" />
              ))}
            </div>
          ) : jobs.length === 0 ? (
            <div
              className="rounded-2xl py-12 text-center"
              style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
            >
              <p className="text-sm" style={{ color: "rgba(255,255,255,0.4)" }}>
                No ingestion jobs yet. Click &ldquo;Ingest from Drive&rdquo; to start.
              </p>
            </div>
          ) : (
            jobs.map((job) => (
              <JobCard key={job.id} job={job} onCancel={cancelJob} />
            ))
          )}
        </div>

        {/* Worker state (1/3) */}
        <div className="space-y-3">
          <h2 className="text-sm font-medium text-white">Worker Summary</h2>
          {stats ? (
            <WorkerState stats={stats} />
          ) : (
            <Skeleton className="h-32 rounded-2xl" />
          )}
        </div>
      </div>
    </div>
  );
}
